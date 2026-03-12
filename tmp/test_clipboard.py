import asyncio
import sys
import os
import threading
import time

# Add current directory and stock_standalone to path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'stock_standalone'))

from tdx_utils import start_clipboard_listener
import pyperclip

class MockSender:
    def send(self, code):
        print(f"MockSender: Sending {code}")

def test_clipboard_logic(keep_clipboard):
    print(f"\nTesting with keep_clipboard={keep_clipboard}")
    sender = MockSender()
    
    # Set initial clipboard content
    test_code = "600000"
    pyperclip.copy(test_code)
    print(f"Initial clipboard: '{pyperclip.paste()}'")
    
    # Start listener
    listener = start_clipboard_listener(sender, timesleep=0.1, keep_clipboard=keep_clipboard)
    
    # Wait for listener to detect and process
    time.sleep(1)
    
    final_content = pyperclip.paste()
    print(f"Final clipboard: '{final_content}'")
    
    if keep_clipboard:
        if final_content == test_code:
            print("PASS: Clipboard preserved")
        else:
            print(f"FAIL: Clipboard changed to '{final_content}'")
    else:
        if final_content == '':
            print("PASS: Clipboard cleared")
        else:
            print(f"FAIL: Clipboard still contains '{final_content}'")

if __name__ == "__main__":
    try:
        test_clipboard_logic(keep_clipboard=False)
        test_clipboard_logic(keep_clipboard=True)
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        print("\nTest finished. Please note that listener threads are daemonized.")
        sys.exit(0)
