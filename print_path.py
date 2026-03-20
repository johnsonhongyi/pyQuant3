
import os
import sys
# Add project root to sys.path
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), 'stock_standalone'))

from bidding_momentum_detector import BiddingMomentumDetector
detector = BiddingMomentumDetector()
print(f"Persistence Path: {detector._get_persistence_path()}")
