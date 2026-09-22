import subprocess
import time
import os

def launch():
    cmd = r'"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\hoang\AppData\Local\EdgeAutomation" --start-maximized http://127.0.0.1:5000/'
    subprocess.run([
        'schtasks', '/create',
        '/tn', 'LaunchEdgeInteractive',
        '/tr', cmd,
        '/sc', 'once',
        '/st', '00:00',
        '/it',
        '/f'
    ], capture_output=True, text=True)

    subprocess.run([
        'schtasks', '/run',
        '/tn', 'LaunchEdgeInteractive'
    ], capture_output=True, text=True)
    print("Edge with CDP port 9222 launched on user desktop!")

if __name__ == "__main__":
    launch()
