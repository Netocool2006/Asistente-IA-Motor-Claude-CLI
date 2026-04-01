import sys, win32file, win32con
ost_path = r'C:\Users\ntoledo\AppData\Local\Microsoft\Outlook\ntoledo@gbm.net.ost'

try:
    handle = win32file.CreateFile(
        ost_path,
        win32con.GENERIC_READ,
        win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
        None, win32con.OPEN_EXISTING, 0, None,
    )
    print("File opened OK")
    _, data = win32file.ReadFile(handle, 512)
    data = bytes(data)
    print(f"Read {len(data)} bytes")
    print("First 32 hex:", data[:32].hex())
    print("Readable?", any(32 <= b < 127 for b in data[:64]))
    win32file.CloseHandle(handle)
except Exception as e:
    print(f"ERROR: {e}")

# Check if file is encrypted (OST encryption header)
import struct
try:
    with open(ost_path, 'rb') as f:
        header = f.read(8)
    print("Direct open header:", header.hex())
except Exception as e:
    print("Direct open error:", e)
