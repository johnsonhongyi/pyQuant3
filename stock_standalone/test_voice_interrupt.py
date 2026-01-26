import sys
import os
import time
from datetime import datetime

# Add the project directory to sys.path
sys.path.append(r'd:\MacTools\WorkFile\WorkSpace\pyQuant3\stock_standalone')

from stock_live_strategy import VoiceAnnouncer

def test_interrupt():
    print(f"[{datetime.now()}] Initializing VoiceAnnouncer...")
    announcer = VoiceAnnouncer()
    time.sleep(2)
    
    print(f"[{datetime.now()}] Queueing 3 long messages...")
    msg1 = "这是第一条很长很长的报警信息，我们要测试它是否能被中间掐断。如果成功，你应该只听到开头的一点点。"
    msg2 = "这是第二条报警信息，它应该在第一条被掐断后正常播放。这证明了队列的连续性。"
    msg3 = "最后一条测试信息。"
    
    announcer.announce(msg1)
    announcer.announce(msg2)
    announcer.announce(msg3)
    
    time.sleep(3) # Let msg1 start
    
    print(f"[{datetime.now()}] TRIGGERING INTERRUPT (Simulating Delete button)...")
    announcer.stop() # This calls stop_current_speech
    
    print(f"[{datetime.now()}] Interrupted. Waiting to see if msg2 and msg3 play...")
    time.sleep(15)
    
    print(f"[{datetime.now()}] Shutdown.")
    announcer.shutdown()
    print(f"[{datetime.now()}] Done.")

if __name__ == "__main__":
    test_interrupt()
