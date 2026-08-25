import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
# Конвертеры импортируются напрямую (from google_to_text import ...): кладём их папку в путь.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "converters")))
