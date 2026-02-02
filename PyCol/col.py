# col.py

import os
import time
import struct
import mmap
import subprocess
from typing import Dict, Any, Optional, List, Tuple

import numpy as np

from .static_flags import (
    G_HDR,
    ACT_BYTES,
    C_HDR,
    HP_BYTES,
    LOG_BYTES,
    FUNC_BYTES,
    ARGS_BYTES,
    HP_OFF,
    LOG_OFF,
    FUNC_OFF,
    ARGS_OFF,
    CAM_OFF,
    ACT_OFF,
    FMT,
    MAX_RESOLUTION,
    BPP,
    BLOCK_STRIDE,
    order,
    MAX_CAMERAS,
)

from .unity_launcher import (
    launch_unity_instance,
    close,
    populate,
    prepare_shm,
    check_unity_readiness,
    parametrize,
    prepare_frames,
)



def depth_rgba8_to_float32(rgba_u8: np.ndarray, near=0.01, far=300) -> np.ndarray:
    """
    Processing the Depth image produced by the Unity shader (that packs a float32
        into R-G-B-A channels.) into a float 1-d array.
    """

    rgba = rgba_u8.astype(np.float32) / 255.0

    k = np.array(
        [
            1.0,
            1.0 / 255.0,
            1.0 / 65025.0,
            1.0 / 160581375.0,
        ],
        dtype=np.float32,
    )

    depth01 = np.tensordot(rgba, k, axes=([-1], [0])) 
    depth01 = near + depth01 * (far - near)
    return depth01


class COL:
    """
    City of Light / Unity shared-memory bridge.

    Wraps:
      - Unity process handle
      - shared-memory mmap
      - camera frame views
      - interaction helpers (move/rotate player, actions, etc.)
    """

    def __init__(
        self,
        unity_exe: str,
        log_dir: str,
        config: Dict[str, Any],
        map_name: str = "paris3d_ipc",
        batch_mode = False,
    ) -> None:
        # Config / paths
        self.unity_exe = unity_exe
        self.log_dir = log_dir
        self.config = config
        self.map_name = map_name
        self.batch_mode = batch_mode

        # Process + shared memory
        self.process: Optional[subprocess.Popen] = None
        self.shm: Optional[mmap.mmap] = None

        # Constants from static_flags
        self.G_HDR = G_HDR
        self.ACT_BYTES = ACT_BYTES
        self.C_HDR = C_HDR
        self.HP_BYTES = HP_BYTES
        self.LOG_BYTES = LOG_BYTES
        self.FUNC_BYTES = FUNC_BYTES
        self.ARGS_BYTES = ARGS_BYTES

        self.HP_OFF = HP_OFF
        self.LOG_OFF = LOG_OFF
        self.FUNC_OFF = FUNC_OFF
        self.ARGS_OFF = ARGS_OFF
        self.CAM_OFF = CAM_OFF
        self.ACT_OFF = ACT_OFF
        self.FMT = FMT

        self.MAX_RESOLUTION = MAX_RESOLUTION
        self.BPP = BPP
        self.BLOCK_STRIDE = BLOCK_STRIDE
        self.order = list(order)
        self.MAX_CAMERAS = MAX_CAMERAS

        # Hyper-parameters and camera frames
        self.HP: Optional[Dict[str, Any]] = None
        self.frames_shm: Optional[Dict[str, np.ndarray]] = None
        self.active_cameras: Optional[List[int]] = None

        # Action index (was global _next)
        self._next: int = 1  


    def launch(self, wait_for_unity: float = 30.0) -> bool:
        """
        Full environment launch sequence.
        Returns True if everything is OK, False otherwise.
        """
        # 1) Hyper-parameters from config
        self.HP = populate(self.config)

        # 2) Launch Unity process
        if self.unity_exe:
            self.process = launch_unity_instance(self.unity_exe, self.log_dir,self.batch_mode)

        # 3) Give Unity some time to start
        #time.sleep(wait_for_unity)
        #time.sleep(30)

        # 4) Attach to shared memory
        self.shm = prepare_shm()

        # 5) Wait for Unity readiness
        unity_ready = check_unity_readiness(self.shm, wait_for_unity)
        if not unity_ready:
            print(
                "Unity is not ready to receive hyperparameters "
                "(COL is not launched yet or there is an instance already running)."
            )
            return False

        # 6) Send hyper-parameters
        unity_parametrized = parametrize(self.shm, self.HP)
        if not unity_parametrized:
            print("Timed out waiting for Unity acknowledgement.")
            return False

        # 7) Prepare frame views
        frames, active = prepare_frames(self.shm, self.HP)
        self.frames_shm = frames
        self.active_cameras = active

        return True

    def close(self) -> None:
        """Closes Unity player and shared memory."""
        if self.shm is not None:
            try:
                self.shm.close()
            except Exception:
                pass
            self.shm = None

        if self.process is not None:
            close(self.process)
            self.process = None



    def move_player(self, x: float, y: float, z: float, wait: bool = True) -> None:
        """
        Request Unity to move the player instantly to (x, y, z). Comments are written to help understand how function processing is handled on Unity side (funcId).
        """
        # 1.  write the three floats into the ARGS block
        self.shm[self.ARGS_OFF : self.ARGS_OFF + 12] = struct.pack("<fff", x, y, z)

        # 2.  set funcId = 1  (MovePlayerTo)
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 1)

        # 3.  optionally wait until Unity zeroes the funcId to signal completion
        if wait:
            while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
                time.sleep(0)
            self.rebuild_chunks()

    def move_goal(self, x: float, y: float, z: float, wait: bool = True) -> None:
        """
        Request Unity to move the goal (a white cube 1-1-1) instantly to (x, y, z). Might be useful for RL experiments.
        """
        self.shm[self.ARGS_OFF : self.ARGS_OFF + 12] = struct.pack("<fff", x, y, z)

        # funcId = 5  (MoveGoalTo)
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 5)

        if wait:
            while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
                time.sleep(0)

    def rotate_player(self, x: float, y: float, z: float, wait: bool = True) -> None:
        """
        Request Unity to rotate the player instantly to (rx, ry, rz).
        """
        self.shm[self.ARGS_OFF : self.ARGS_OFF + 12] = struct.pack("<fff", x, y, z)

        # funcId = 4  (RotatePlayerTo)
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 4)

        if wait:
            while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
                time.sleep(0)

    def rebuild_chunks(self) -> None:
        # func id = 4
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 2)
        while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
            time.sleep(0)

    def force_camera_read(self) -> None:
        """Requests for camera rendering."""
        #func id = 3
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 3)
        while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
            time.sleep(0.001)

    def write_action(self, fwd: int, turn: int, vert: int, grav: int) -> None:
        """Send one 5-int packet; Unity will step exactly once but won't wait for frames."""
        self.shm.seek(self.ACT_OFF)
        self.shm.write(struct.pack(self.FMT, self._next, fwd, turn, vert, grav))
        self._next += 1

    def run_N_blank_timesteps(self, n: int) -> None:
        for _ in range(n):
            self.write_action_until_frame(0, 0, 0, 0)

    def write_action_until_frame(
        self, fwd: int, turn: int, vert: int, grav: int
    ) -> None:
        """ Write an action for the main agent and waits for cameras rendering after step (filled in self.frames_shm)."""
        

        last_update_index = struct.unpack_from("<I", self.shm, 0)[0]
        self.write_action(fwd, turn, vert, grav)
        while True:
            update_index = struct.unpack_from("<I", self.shm, 0)[0]
            if last_update_index != update_index:
                last_update_index = update_index
                break
            time.sleep(0)  



    def extract_visual_frames(self,far = 300) -> List[np.ndarray]:
        """
        Convert frames buffers to uint8 images (for visualization).
        """
        actives = list(
            (lbl for lbl, flag in zip(self.order, self.active_cameras) if flag)
        )
        result: List[np.ndarray] = []
        for key in actives:
            if key == "Depth":
                depth_raw = (
                    np.expand_dims(
                        depth_rgba8_to_float32(self.frames_shm["Depth"]), -1
                    ).repeat(3, -1)
                )
                depth = ((depth_raw / far) * 1000).clip(0, 255).astype(
                    np.uint8
                )  # *255 normally, here *1000 just to improve low distance contrast
                img = depth[::-1]
            else:
                img = self.frames_shm[key][:, :, 0:3][::-1, :]
            result.append(img)
        return result

    def extract_xyz(self) -> Tuple[float, float, float, float, float, float]:
        """
        Extract 6DoF from unity.
        """
        _, _, px, py, pz, rx, ry, rz = struct.unpack_from(
            "<IIffffff", self.shm, 0
        )
        return (px, py, pz, rx, ry, rz)

    def extract_collisions(self) -> np.ndarray:
        return np.array(struct.unpack_from("16B", self.shm, 32))

    def promote_chunk(self, chunk_idx: int, wait: bool = True) -> None:
        """
        Promote a specific chunk. No timeout; waits for Unity to ACK unless wait=False.

        """
        # a0 = chunk index as float; a1/a2 unused
        self.shm[self.ARGS_OFF : self.ARGS_OFF + 12] = struct.pack(
            "<fff", float(int(chunk_idx)), 0.0, 0.0
        )
        # func_id = 6
        self.shm[self.FUNC_OFF : self.FUNC_OFF + 4] = struct.pack("<I", 6)

        if not wait:
            return

        try:
            while struct.unpack_from("<I", self.shm, self.FUNC_OFF)[0] != 0:
                time.sleep(0)  # cooperative yield
        except KeyboardInterrupt:
            # allow manual abort without crashing your session
            pass
