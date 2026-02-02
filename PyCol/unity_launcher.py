import os, subprocess, signal, ctypes, time, mmap, struct
import numpy as np
from .static_flags import *


def _pdeathsig_preexec(sig=signal.SIGTERM):
    """
    On Linux preparing a child's process is easier thanks to prctlr.
    If the parent dies, the kernel sends `sig` to this process to stop it.
    """
    def _fn():
        libc = ctypes.CDLL("libc.so.6", use_errno=True)
        PR_SET_PDEATHSIG = 1
        # If parent already gone between fork and this call, bail out.
        if os.getppid() == 1:
            os._exit(1)
        if libc.prctl(PR_SET_PDEATHSIG, sig) != 0:
            # On error, still proceed; Unity will just not auto-exit on parent death.
            pass
    return _fn
    
# We need windows specific imports to reproduce linux's prctlr behavior (python killed -> unity killed)
if os.name == "nt":
    import ctypes.wintypes as wt

    if not hasattr(wt, "SIZE_T"):
        wt.SIZE_T = ctypes.c_size_t
    
    if not hasattr(wt, "ULONG_PTR"):
        wt.ULONG_PTR = ctypes.c_size_t
        
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wt.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wt.LARGE_INTEGER),
            ("LimitFlags", wt.DWORD),
            ("MinimumWorkingSetSize", wt.SIZE_T),
            ("MaximumWorkingSetSize", wt.SIZE_T),
            ("ActiveProcessLimit", wt.DWORD),
            ("Affinity", wt.ULONG_PTR),
            ("PriorityClass", wt.DWORD),
            ("SchedulingClass", wt.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", wt.ULARGE_INTEGER),
            ("WriteOperationCount", wt.ULARGE_INTEGER),
            ("OtherOperationCount", wt.ULARGE_INTEGER),
            ("ReadTransferCount", wt.ULARGE_INTEGER),
            ("WriteTransferCount", wt.ULARGE_INTEGER),
            ("OtherTransferCount", wt.ULARGE_INTEGER),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", wt.SIZE_T),
            ("JobMemoryLimit", wt.SIZE_T),
            ("PeakProcessMemoryUsed", wt.SIZE_T),
            ("PeakJobMemoryUsed", wt.SIZE_T),
        ]

    kernel32.CreateJobObjectW.argtypes = [wt.LPVOID, wt.LPCWSTR]
    kernel32.CreateJobObjectW.restype  = wt.HANDLE

    kernel32.SetInformationJobObject.argtypes = [wt.HANDLE, wt.INT, wt.LPVOID, wt.DWORD]
    kernel32.SetInformationJobObject.restype  = wt.BOOL

    kernel32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]
    kernel32.AssignProcessToJobObject.restype  = wt.BOOL

    def _create_kill_on_close_job():
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = kernel32.SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise ctypes.WinError(ctypes.get_last_error())

        return job

    def _assign_pid_to_job(job_handle, pid: int):
        # Apparently, OpenProcess is safer than Popen._handle
        PROCESS_ALL_ACCESS = 0x1F0FFF
        hproc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not hproc:
            raise ctypes.WinError(ctypes.get_last_error())

        ok = kernel32.AssignProcessToJobObject(job_handle, hproc)
        if not ok:
            err = ctypes.get_last_error()
            kernel32.CloseHandle(hproc)
            raise ctypes.WinError(err)

        kernel32.CloseHandle(hproc)


def launch_unity_instance(UNITY_EXE,LOG_DIR, batch_mode=False, *extra_args):
    """
    Launch Unity; it will receive SIGTERM automatically if this Python process dies.
    Returns a subprocess.Popen handle.
    """


    args = [
        UNITY_EXE,
        "-screen-fullscreen", "0",
        "-screen-width", "100",
        "-screen-height", "100",
        "-logFile", os.path.join(LOG_DIR, "logs.log"),
    ]

    # ─── Conditional batch/headless mode ───
    if batch_mode:
        args += [
            "-batchmode",   # disables the Unity Editor UI, makes it non-interactive
        ]
    args += list(extra_args)

    return subprocess.Popen(args, preexec_fn=_pdeathsig_preexec(signal.SIGTERM))


def launch_unity_instance(UNITY_EXE, LOG_DIR, batch_mode=False, *extra_args):
    """
    Launch Unity with parent-death behavior:
      - posix: prctl(PDEATHSIG) -> Unity gets SIGTERM if Python dies
      - nt / rt: Job Object KILL_ON_JOB_CLOSE -> Unity killed if Python dies

    Adds Turbo launch arg for your Unity LaunchArgsBoot:
      turbo=True  -> --turbo
      turbo=False -> --turbo=0
      turbo=None  -> (no arg)
    """

    args = [
        UNITY_EXE,
        "-screen-fullscreen", "0",
        "-screen-width", "100",
        "-screen-height", "100",
        "-logFile", os.path.join(LOG_DIR, "logs.log"),
    ]

    if batch_mode:
        args += ["-batchmode"]

    args += ["--turbo"]


    args += list(extra_args)

    if os.name == "posix":
        return subprocess.Popen(args, preexec_fn=_pdeathsig_preexec(signal.SIGTERM))

    elif os.name == "nt":
        proc = subprocess.Popen(args)

        job = _create_kill_on_close_job()
        try:
            _assign_pid_to_job(job, proc.pid)
        except Exception:
            kernel32.CloseHandle(job)
            raise

        # keep job handle alive / closing it kills Unity
        proc._job_handle = job
        return proc

    elif os.name == "rt":
        proc = subprocess.Popen(args)

        job = _create_kill_on_close_job()
        try:
            _assign_pid_to_job(job, proc.pid)
        except Exception:
            kernel32.CloseHandle(job)
            raise

        proc._job_handle = job
        return proc

    else:
        print("OS not supported")
        return None



def close(proc):
    """Closes Unity player."""
    if proc.poll() is None:
        proc.terminate()          
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()           
            
def populate(config):
    HP = {
    "speedFactor":     config['speed_factor'],
    "spawnPeds":       config['spawn_pedestrians'],
    "spawnCars":       config['spawn_cars'],
    "moveSpeed":       config['move_speed'],
    "turnSpeed":       config['turn_speed'],
    "verticalSpeed":   config['vertical_speed'],
    "momentum":        config['momentum'],
    "fixedDeltaTime":  config['fixedDeltaTime'],
    "nActions":        config['number_of_steps'],
    "rgb":             config['rgb_camera'],
    "depth":           config['depth_camera'],
    "normals":         config['normals_camera'],
    "semantic":        config['semantic_camera'],
    "imageWidth":      config['IMG_SIZE'],          
    "imageHeight":     config['IMG_SIZE'],         
    "vFOV":            config['vertical_fov'],        
    "startX":          config['start_x'],
    "startY":          config['start_y'],
    "startZ":          config['start_z'],
    "launch_streaming":config['launch_streaming'],
    "render":          config['render']
    }
    return(HP)
    
    
def shm_size_bytes():
    CAM_OFF = G_HDR + ACT_BYTES + HP_BYTES + LOG_BYTES + FUNC_BYTES + ARGS_BYTES
    bytes_per_cam = C_HDR + MAX_RESOLUTION * MAX_RESOLUTION * BPP
    return CAM_OFF + bytes_per_cam * MAX_CAMERAS
    
def prepare_shm(MAP_NAME = "paris3d_ipc", timeout: float = 30.0):
    """
    Prepares the shared memory segment for python.
    Waits (up to 'timeout' seconds) for Unity to create /dev/shm/<MAP_NAME>.
    """

    if os.name == 'posix':
        shm_path = f"/dev/shm/{MAP_NAME}"

        # Wait until Unity creates the shared memory file
        start = time.time()
        while not os.path.exists(shm_path):
            if time.time() - start > timeout:
                raise FileNotFoundError(
                    f"Shared memory file {shm_path} not found after {timeout}s. "
                    "Unity may not have started yet."
                )
            time.sleep(0.1)

        fd = os.open(shm_path, os.O_RDWR)
        shm = mmap.mmap(fd, 0, access=mmap.ACCESS_WRITE)
        os.close(fd)

    else:
        size = shm_size_bytes()
        shm = mmap.mmap(-1, size, tagname=MAP_NAME, access=mmap.ACCESS_WRITE)

    return shm

    
def check_unity_readiness(shm, timeout: float = 3.0) -> bool:
    """
    Wait until Unity signals readiness (HP_OFF == 0).
    """
    deadline = time.time() + timeout
    while True:
        if struct.unpack_from("<I", shm, HP_OFF)[0] == 0:
            return True
        if timeout > 0 and time.time() >= deadline:
            return False
        time.sleep(0.01)  # avoiding busy spin
    
def parametrize(shm, HP, timeout: float = 30) -> float:
    """
    Send hyper-parameters and wait for Unity to acknowledge (HP_OFF -> 2).
    """
    hp_fmt  = "<fII5f9I4f"
    hp_blob = struct.pack(
        hp_fmt,
        HP["speedFactor"],
        HP["spawnPeds"],  HP["spawnCars"],
        HP["moveSpeed"],  HP["turnSpeed"],  HP["verticalSpeed"],
        HP["momentum"],   HP["fixedDeltaTime"],
        HP["nActions"],
        HP["rgb"],        HP["depth"],      HP["normals"],
        HP["semantic"],   HP["launch_streaming"], HP["render"], HP["imageWidth"], HP["imageHeight"],
        HP["vFOV"],
        HP["startX"],     HP["startY"],     HP["startZ"],
    )

    # Send
    shm[HP_OFF + 4 : HP_OFF + 4 + HP_BYTES] = hp_blob
    shm[HP_OFF : HP_OFF + 4] = struct.pack("<I", 1)  # hpState = 1 (pending)
    print("▶ hyper-parameters sent – waiting for Unity …")

    t0 = time.monotonic()
    while True:
        if struct.unpack_from("<I", shm, HP_OFF)[0] == 2:  # Awknowledgement
            elapsed = time.monotonic() - t0
            print("✔ Unity acknowledged hyper-parameters – simulation running")
            return True
        else:
            shm[HP_OFF + 4 : HP_OFF + 4 + HP_BYTES] = hp_blob
            shm[HP_OFF : HP_OFF + 4] = struct.pack("<I", 1)  # hpState = 1 (pending)
            time.sleep(0.1)

        if timeout is not None and (time.monotonic() - t0) >= timeout:
            return(False)



def prepare_frames(shm, HP):
    frames = {}
    frame_idx, n_cam, px, py, pz, rx, ry, rz = struct.unpack_from("<IIffffff", shm, 0)
    print(f"{n_cam} camera(s) – player at ({px:.2f}, {py:.2f}, {pz:.2f})")
    
    active     = [HP["rgb"], HP["depth"], HP["normals"], HP["semantic"]]
    label_iter = (lbl for lbl, flag in zip(order, active) if flag)
    
    off = CAM_OFF
    for cam_idx in range(n_cam):
        cid, w, h, chan = struct.unpack_from("<IIII", shm, off)
        pix_off   = off + C_HDR
        pix_bytes = w * h * chan
    
        label = next(label_iter, f"cam{cam_idx}")
        print(f"{label}: {w}×{h}  chan={chan}  off=0x{pix_off:X}")
    
        BufType = ctypes.c_uint8 * pix_bytes
        buf     = BufType.from_buffer(shm, pix_off)
        frame   = np.frombuffer(buf, dtype=np.uint8).reshape(h, w, chan)
        frames[label] = frame
    
        off += BLOCK_STRIDE
    return(frames,active)