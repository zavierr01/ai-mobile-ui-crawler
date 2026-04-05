"""Entry point for mobile-crawler GUI application."""

#!/usr/bin/env python
"""Entry point for mobile-crawler GUI application with fixed path."""

import sys
import os

# Add src directory to path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

from mobile_crawler.ui.main_window import run

if __name__ == "__main__":
    run()
