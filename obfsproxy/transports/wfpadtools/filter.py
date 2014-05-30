"""
This module implements the class PadFilter which is used to
filter padding messages from Tor data messages.
"""

class PadFilter(object):
    """Implement methods to filter padding messages out."""

    def __init__(self):
        pass
    
    def filter(self, data):
        """Return None if data is padding."""
        return data
