import uvicorn
import os
import sys

# Ensure UTF-8 output encoding on Windows console
if sys.platform.startswith("win"):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

if __name__ == "__main__":
    print("=" * 65)
    print("  Starting Cafy Agent (ATS Scraper & Job Recommendation Engine)")
    print("  Supported ATS: Greenhouse, Ashby, Lever, Workday,")
    print("                 Workable, Oracle Cloud, BreezyHR, Pinpoint")
    print("  React UI & API at: http://127.0.0.1:8000")
    print("=" * 65)
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
