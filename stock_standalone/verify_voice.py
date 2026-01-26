import sys
import os
import time
from datetime import datetime

# Add the project directory to sys.path
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from stock_live_strategy import VoiceAnnouncer

def test_voice():
    print(f"[{datetime.now()}] Initializing VoiceAnnouncer...")
    try:
        announcer = VoiceAnnouncer()
        print(f"[{datetime.now()}] Announcer initialized. Waiting 2 seconds for worker startup...")
        time.sleep(2)
        
        msg = "测试报警系统，语音播报测试。如果听到这句话，说明修复成功。"
        print(f"[{datetime.now()}] Announcing: {msg}")
        announcer.announce(msg)
        
        print(f"[{datetime.now()}] Waiting 10 seconds for playback to finish...")
        time.sleep(10)
        
        print(f"[{datetime.now()}] Shutdown.")
        announcer.shutdown()
        print(f"[{datetime.now()}] Done.")
    except Exception as e:
        print(f"[{datetime.now()}] Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_voice()
