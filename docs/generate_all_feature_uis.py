import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent / "doc_assets"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# Modern UI Color Palette
BG_WINDOW = (248, 250, 252)      # Slate-50
BG_NAVBAR = (15, 23, 42)         # Slate-900
BG_CARD = (255, 255, 255)        # Pure White
BG_CARD_SUBTLE = (241, 245, 249) # Slate-100
BORDER_COLOR = (226, 232, 240)   # Slate-200
BORDER_DARK = (203, 213, 225)    # Slate-300

TEXT_TITLE = (15, 23, 42)        # Slate-900
TEXT_BODY = (51, 65, 85)         # Slate-700
TEXT_MUTED = (100, 116, 139)     # Slate-500
TEXT_LIGHT = (255, 255, 255)

PRIMARY_BLUE = (37, 99, 235)     # #2563EB
PRIMARY_BLUE_BG = (239, 246, 255)# #EFF6FF
SUCCESS_GREEN = (16, 185, 129)   # #10B981
SUCCESS_GREEN_BG = (236, 253, 245)
AMBER_WARN = (217, 119, 6)       # Amber-600
AMBER_BG = (254, 243, 199)
PURPLE_ACC = (124, 58, 237)      # Violet-600
PURPLE_BG = (245, 243, 255)
RED_ALERT = (220, 38, 38)
RED_BG = (254, 242, 242)

FONT_REG = "C:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C:/Windows/Fonts/segoeuib.ttf"
FONT_SEMI = "C:/Windows/Fonts/segoeuisl.ttf"

def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)

def draw_header(draw, title_tab, width=1280):
    # Top OS Bar / App Navigation
    draw.rectangle([0, 0, width, 64], fill=BG_NAVBAR)
    
    # App Logo
    draw.rounded_rectangle([20, 16, 48, 48], radius=8, fill=PRIMARY_BLUE)
    draw.text((28, 20), "C", fill=TEXT_LIGHT, font=font(20, bold=True))
    draw.text((58, 20), "Cafy Agent", fill=TEXT_LIGHT, font=font(18, bold=True))
    draw.text((156, 24), "• UK Enterprise Career Intelligence", fill=(148, 163, 184), font=font(12))

    tabs = [
        ("Find UK Jobs", title_tab == "jobs"),
        ("Resume Studio", title_tab == "resume"),
        ("My Applications", title_tab == "applications"),
        ("Email Agent", title_tab == "email"),
        ("UK Sponsors", title_tab == "sponsors"),
    ]
    
    x = 420
    for name, is_active in tabs:
        t_len = int(font(13).getlength(name))
        if is_active:
            draw.rounded_rectangle([x - 12, 14, x + t_len + 12, 50], radius=8, fill=PRIMARY_BLUE)
            draw.text((x, 22), name, fill=TEXT_LIGHT, font=font(13, bold=True))
        else:
            draw.text((x, 22), name, fill=(203, 213, 225), font=font(13))
        x += t_len + 36

    # Candidate profile badge
    draw.rounded_rectangle([width - 190, 16, width - 20, 48], radius=20, fill=(30, 41, 59))
    draw.ellipse([width - 186, 20, width - 156, 44], fill=PRIMARY_BLUE)
    draw.text((width - 177, 24), "SA", fill=TEXT_LIGHT, font=font(11, bold=True))
    draw.text((width - 148, 24), "Samyukta A.", fill=TEXT_LIGHT, font=font(12, bold=True))

def draw_pill(draw, box, text, bg_col, text_col, border_col=None):
    draw.rounded_rectangle(box, radius=6, fill=bg_col, outline=border_col, width=1 if border_col else 0)
    tx = box[0] + 10
    ty = box[1] + (box[3] - box[1] - 14) // 2
    draw.text((tx, ty), text, fill=text_col, font=font(11, bold=True))

# -------------------------------------------------------------
# 1. UI: UK JOB DIRECTORY & DISCOVERY
# -------------------------------------------------------------
def build_ui_job_directory():
    W, H = 1280, 780
    img = Image.new("RGB", (W, H), BG_WINDOW)
    draw = ImageDraw.Draw(img)
    draw_header(draw, "jobs", W)

    # Sub-header bar
    draw.rectangle([0, 64, W, 120], fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((28, 78), "UK Job Discovery & Visa Sponsorship Search", fill=TEXT_TITLE, font=font(18, bold=True))
    draw.text((28, 100), "Strictly verified UK vacancies with real-time Home Office Skilled Worker sponsor matching", fill=TEXT_MUTED, font=font(12))
    
    # Live stats chips
    draw_pill(draw, [W - 480, 80, W - 320, 108], "3,482 Active UK Jobs", PRIMARY_BLUE_BG, PRIMARY_BLUE, BORDER_COLOR)
    draw_pill(draw, [W - 308, 80, W - 140, 108], "1,215 Verified Sponsors", SUCCESS_GREEN_BG, SUCCESS_GREEN, BORDER_COLOR)
    draw_pill(draw, [W - 128, 80, W - 20, 108], "Strict UK Only", (241, 245, 249), TEXT_TITLE, BORDER_COLOR)

    # Left Filter Sidebar
    draw.rounded_rectangle([24, 136, 320, 750], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((44, 154), "Refine Discovery", fill=TEXT_TITLE, font=font(15, bold=True))
    
    # Filter 1: Keywords
    draw.text((44, 190), "ROLE OR KEYWORD", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([44, 210, 300, 248], radius=8, fill=BG_CARD_SUBTLE, outline=BORDER_COLOR, width=1)
    draw.text((56, 220), "Software Engineer, Cloud...", fill=TEXT_BODY, font=font(12))

    # Filter 2: UK Municipal Corridor
    draw.text((44, 268), "UK LOCATION", fill=TEXT_MUTED, font=font(11, bold=True))
    locs = [("All UK Locations", True), ("London (1,842)", False), ("Manchester (384)", False), ("Edinburgh (210)", False), ("UK Remote (620)", False)]
    ly = 290
    for l_text, is_chk in locs:
        draw.rounded_rectangle([44, ly, 60, ly + 16], radius=4, fill=PRIMARY_BLUE if is_chk else BG_CARD, outline=PRIMARY_BLUE if is_chk else BORDER_DARK, width=1)
        if is_chk:
            draw.text((48, ly), "v", fill=TEXT_LIGHT, font=font(10, bold=True))
        draw.text((70, ly), l_text, fill=TEXT_TITLE if is_chk else TEXT_BODY, font=font(12, bold=is_chk))
        ly += 28

    # Filter 3: Visa Sponsorship
    draw.text((44, 440), "IMMIGRATION & SPONSORSHIP", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([44, 462, 300, 502], radius=8, fill=SUCCESS_GREEN_BG, outline=SUCCESS_GREEN, width=1)
    draw.text((56, 474), "[X] Verified Skilled Worker Sponsor", fill=SUCCESS_GREEN, font=font(12, bold=True))

    # Filter 4: Salary Range (GBP)
    draw.text((44, 524), "MINIMUM SALARY (GBP)", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([44, 546, 300, 584], radius=8, fill=BG_CARD_SUBTLE, outline=BORDER_COLOR, width=1)
    draw.text((56, 556), "£55,000+ per annum", fill=TEXT_TITLE, font=font(12, bold=True))

    # Right Content Area: Job Cards
    cards = [
        {
            "title": "Senior Cloud Infrastructure Engineer (AWS / Kubernetes)",
            "company": "Deliveroo UK Ltd",
            "loc": "London, United Kingdom • Hybrid",
            "salary": "£85,000 - £105,000 GBP",
            "ats": "Greenhouse",
            "match": "94% Job Match",
            "sponsor": "Licensed Skilled Worker Sponsor",
            "skills": ["AWS", "Kubernetes", "Terraform", "Docker", "Python", "Prometheus"]
        },
        {
            "title": "Full Stack Platform Developer",
            "company": "Monzo Bank Ltd",
            "loc": "London, United Kingdom • UK Remote",
            "salary": "£75,000 - £90,000 GBP",
            "ats": "Ashby",
            "match": "89% Job Match",
            "sponsor": "Licensed Skilled Worker Sponsor",
            "skills": ["Go", "React", "TypeScript", "PostgreSQL", "Kafka", "Microservices"]
        },
        {
            "title": "Backend Systems Software Engineer",
            "company": "Arm Limited",
            "loc": "Cambridge, United Kingdom • On-site",
            "salary": "£70,000 - £88,000 GBP",
            "ats": "Workday",
            "match": "82% Job Match",
            "sponsor": "Licensed Skilled Worker Sponsor",
            "skills": ["C++", "Python", "Linux Kernel", "CI/CD", "Git"]
        }
    ]

    cy = 136
    for c in cards:
        draw.rounded_rectangle([344, cy, W - 24, cy + 188], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
        
        # Match Score Badge
        draw_pill(draw, [W - 170, cy + 18, W - 44, cy + 46], c["match"], PURPLE_BG, PURPLE_ACC, BORDER_COLOR)
        
        # Title & Company
        draw.text((368, cy + 18), c["title"], fill=TEXT_TITLE, font=font(16, bold=True))
        draw.text((368, cy + 44), f"{c['company']}  •  {c['loc']}", fill=TEXT_BODY, font=font(13))
        
        # Tags row
        draw_pill(draw, [368, cy + 74, 520, cy + 102], c["salary"], (241, 245, 249), TEXT_TITLE)
        draw_pill(draw, [530, cy + 74, 760, cy + 102], c["sponsor"], SUCCESS_GREEN_BG, SUCCESS_GREEN)
        draw_pill(draw, [770, cy + 74, 850, cy + 102], f"ATS: {c['ats']}", BG_CARD_SUBTLE, TEXT_MUTED)

        # Skill tags
        sx = 368
        for s in c["skills"]:
            slen = int(font(11).getlength(s)) + 16
            draw.rounded_rectangle([sx, cy + 116, sx + slen, cy + 138], radius=6, fill=BG_CARD_SUBTLE)
            draw.text((sx + 8, cy + 120), s, fill=TEXT_BODY, font=font(11))
            sx += slen + 8

        # Action Buttons
        draw.rounded_rectangle([368, cy + 148, 490, cy + 176], radius=6, fill=PRIMARY_BLUE)
        draw.text((388, cy + 154), "Tailor Resume", fill=TEXT_LIGHT, font=font(12, bold=True))
        
        draw.rounded_rectangle([500, cy + 148, 620, cy + 176], radius=6, fill=BG_CARD, outline=BORDER_DARK, width=1)
        draw.text((526, cy + 154), "Apply Directly", fill=TEXT_TITLE, font=font(12, bold=True))

        cy += 200

    out = ASSETS_DIR / "ui_feature_job_directory.png"
    img.save(out)
    return str(out)

# -------------------------------------------------------------
# 2. UI: APPLICATION LIFECYCLE & KANBAN TRACKER
# -------------------------------------------------------------
def build_ui_applications_kanban():
    W, H = 1280, 780
    img = Image.new("RGB", (W, H), BG_WINDOW)
    draw = ImageDraw.Draw(img)
    draw_header(draw, "applications", W)

    # Sub-header
    draw.rectangle([0, 64, W, 120], fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((28, 78), "Candidate Application Pipeline & Stage Management", fill=TEXT_TITLE, font=font(18, bold=True))
    draw.text((28, 100), "Real-time state tracking integrated with autonomous email agent polling and calendar alerts", fill=TEXT_MUTED, font=font(12))

    columns = [
        ("APPLIED (8)", [
            {"role": "Cloud DevOps Engineer", "comp": "Deliveroo UK", "date": "Applied 2d ago", "tag": "Pending Confirmation"},
            {"role": "Backend Engineer", "comp": "Checkout.com", "date": "Applied 5d ago", "tag": "Under Review"}
        ], (241, 245, 249)),
        ("SCREENING (3)", [
            {"role": "Full Stack Platform Dev", "comp": "Monzo Bank", "date": "Recruiter Call Scheduled", "tag": "Call: Nov 5, 2:00 PM", "hl": PRIMARY_BLUE_BG}
        ], PRIMARY_BLUE_BG),
        ("ASSESSMENT (2)", [
            {"role": "Software Systems Engineer", "comp": "Wise UK Ltd", "date": "Take-Home Project", "tag": "Deadline: 3 days left", "hl": AMBER_BG}
        ], AMBER_BG),
        ("INTERVIEWING (2)", [
            {"role": "AWS Infrastructure Intern", "comp": "Figma UK", "date": "Final Round (System Design)", "tag": "Auto-Advanced via Email", "hl": SUCCESS_GREEN_BG}
        ], SUCCESS_GREEN_BG),
        ("OFFER (1)", [
            {"role": "Lead Site Reliability Eng", "comp": "Revolut UK", "date": "£95,000 GBP Compensation", "tag": "Formal Offer Received", "hl": PURPLE_BG}
        ], PURPLE_BG)
    ]

    col_w = (W - 48 - 4 * 16) // 5
    cx = 24
    for col_title, items, header_bg in columns:
        draw.rounded_rectangle([cx, 136, cx + col_w, 750], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
        
        # Col Header
        draw.rounded_rectangle([cx, 136, cx + col_w, 176], radius=12, fill=header_bg)
        draw.rectangle([cx, 160, cx + col_w, 176], fill=header_bg)
        draw.text((cx + 14, 148), col_title, fill=TEXT_TITLE, font=font(12, bold=True))

        iy = 190
        for itm in items:
            hl = itm.get("hl", BG_CARD_SUBTLE)
            draw.rounded_rectangle([cx + 12, iy, cx + col_w - 12, iy + 130], radius=10, fill=BG_CARD, outline=BORDER_COLOR, width=1)
            draw.text((cx + 24, iy + 14), itm["comp"], fill=PRIMARY_BLUE, font=font(12, bold=True))
            draw.text((cx + 24, iy + 34), itm["role"], fill=TEXT_TITLE, font=font(13, bold=True))
            draw.text((cx + 24, iy + 58), itm["date"], fill=TEXT_MUTED, font=font(11))
            
            # Badge
            draw.rounded_rectangle([cx + 24, iy + 84, cx + col_w - 24, iy + 112], radius=6, fill=hl)
            draw.text((cx + 34, iy + 92), itm["tag"], fill=TEXT_TITLE, font=font(11, bold=True))

            iy += 146

        cx += col_w + 16

    out = ASSETS_DIR / "ui_feature_application_tracker.png"
    img.save(out)
    return str(out)

# -------------------------------------------------------------
# 3. UI: AUTONOMOUS EMAIL AGENT DASHBOARD
# -------------------------------------------------------------
def build_ui_email_agent():
    W, H = 1280, 780
    img = Image.new("RGB", (W, H), BG_WINDOW)
    draw = ImageDraw.Draw(img)
    draw_header(draw, "email", W)

    # Sub-header
    draw.rectangle([0, 64, W, 120], fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((28, 78), "Autonomous Recruiter Email Agent & Follow-Up Hub", fill=TEXT_TITLE, font=font(18, bold=True))
    draw.text((28, 100), "Multi-class incoming recruiter classifier with automated pipeline sync and pre-drafted response engine", fill=TEXT_MUTED, font=font(12))

    # Connection Status Pill
    draw_pill(draw, [W - 320, 80, W - 24, 108], "IMAP / OAuth2 Sync Active", SUCCESS_GREEN_BG, SUCCESS_GREEN, BORDER_COLOR)

    # Left: Incoming Intelligence Stream
    draw.rounded_rectangle([24, 136, 560, 750], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((44, 154), "Recent Recruiter Messages (6-Class Classified)", fill=TEXT_TITLE, font=font(15, bold=True))

    msgs = [
        {
            "sender": "Deliveroo Talent Acquisition <no-reply@greenhouse-mail.io>",
            "subject": "Interview Invitation: Senior Cloud Infrastructure Engineer",
            "class": "Interview Invitation",
            "action": "Advanced to 'Interviewing' • Pre-drafted reply ready",
            "bg": SUCCESS_GREEN_BG, "col": SUCCESS_GREEN
        },
        {
            "sender": "Wise Engineering Team <recruiting@wise.com>",
            "subject": "Next Steps: Software Systems Technical Assessment",
            "class": "Technical Assessment",
            "action": "Deadline detected: Friday 5:00 PM BST • Calendar alert set",
            "bg": AMBER_BG, "col": AMBER_WARN
        },
        {
            "sender": "Monzo Careers <jobs@ashbyhq.com>",
            "subject": "Application Received: Full Stack Platform Developer",
            "class": "Acknowledgment",
            "action": "Acknowledged • Cadence timer started (Day 4 of 7)",
            "bg": PRIMARY_BLUE_BG, "col": PRIMARY_BLUE
        }
    ]

    my = 190
    for m in msgs:
        draw.rounded_rectangle([44, my, 540, my + 158], radius=10, fill=BG_WINDOW, outline=BORDER_COLOR, width=1)
        draw.text((58, my + 14), m["sender"], fill=TEXT_MUTED, font=font(11))
        draw.text((58, my + 34), m["subject"], fill=TEXT_TITLE, font=font(13, bold=True))
        
        draw_pill(draw, [58, my + 64, 230, my + 92], m["class"], m["bg"], m["col"])
        draw.text((58, my + 104), f"Status: {m['action']}", fill=TEXT_BODY, font=font(11, bold=True))
        my += 174

    # Right: Pre-Drafted Action Box
    draw.rounded_rectangle([580, 136, W - 24, 750], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((604, 154), "Autonomous Response Drafter (Human-in-the-Loop Approval)", fill=TEXT_TITLE, font=font(15, bold=True))
    draw_pill(draw, [W - 200, 150, W - 44, 178], "Ready for Review", PRIMARY_BLUE_BG, PRIMARY_BLUE)

    # To / Subject fields
    draw.text((604, 200), "RECIPIENT", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([604, 220, W - 44, 256], radius=6, fill=BG_CARD_SUBTLE, outline=BORDER_COLOR, width=1)
    draw.text((616, 230), "talent-team@deliveroo.co.uk", fill=TEXT_TITLE, font=font(12))

    draw.text((604, 272), "SUBJECT", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([604, 292, W - 44, 328], radius=6, fill=BG_CARD_SUBTLE, outline=BORDER_COLOR, width=1)
    draw.text((616, 302), "Re: Interview Invitation - Senior Cloud Infrastructure Engineer (Samyukta A.)", fill=TEXT_TITLE, font=font(12))

    draw.text((604, 344), "SUGGESTED PROFESSIONAL RESPONSE", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.rounded_rectangle([604, 364, W - 44, 630], radius=8, fill=BG_CARD_SUBTLE, outline=BORDER_COLOR, width=1)
    
    email_lines = [
        "Dear Deliveroo Talent Team,",
        "",
        "Thank you very much for considering my application and extending this invitation to interview",
        "for the Senior Cloud Infrastructure Engineer position.",
        "",
        "I am very excited about Deliveroo's container orchestration and multi-region AWS cloud platform.",
        "I confirm my availability for the technical conversation during either of the following slots:",
        "  • Thursday, November 6th at 10:00 AM BST",
        "  • Friday, November 7th at 2:30 PM BST",
        "",
        "Looking forward to speaking with the engineering team.",
        "",
        "Best regards,",
        "Samyukta A."
    ]
    ely = 380
    for el in email_lines:
        draw.text((620, ely), el, fill=TEXT_BODY, font=font(12))
        ely += 16

    # Action buttons
    draw.rounded_rectangle([604, 656, 760, 696], radius=8, fill=PRIMARY_BLUE)
    draw.text((634, 668), "Approve & Send", fill=TEXT_LIGHT, font=font(13, bold=True))

    draw.rounded_rectangle([772, 656, 890, 696], radius=8, fill=BG_CARD, outline=BORDER_DARK, width=1)
    draw.text((804, 668), "Edit Draft", fill=TEXT_TITLE, font=font(13, bold=True))

    out = ASSETS_DIR / "ui_feature_email_agent.png"
    img.save(out)
    return str(out)

# -------------------------------------------------------------
# 4. UI: UK SPONSORING EMPLOYERS REGISTRY
# -------------------------------------------------------------
def build_ui_sponsor_registry():
    W, H = 1280, 780
    img = Image.new("RGB", (W, H), BG_WINDOW)
    draw = ImageDraw.Draw(img)
    draw_header(draw, "sponsors", W)

    # Sub-header
    draw.rectangle([0, 64, W, 120], fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((28, 78), "Official UK Home Office Licensed Sponsor Directory", fill=TEXT_TITLE, font=font(18, bold=True))
    draw.text((28, 100), "Search and verify licensed UK employers authorised to sponsor Skilled Worker and Global Business Mobility visas", fill=TEXT_MUTED, font=font(12))

    # Search Bar
    draw.rounded_rectangle([24, 136, W - 24, 186], radius=10, fill=BG_CARD, outline=BORDER_COLOR, width=1)
    draw.text((44, 152), "Search by employer name, industry, or UK city...", fill=TEXT_MUTED, font=font(13))
    draw_pill(draw, [W - 160, 144, W - 36, 178], "Search Register", PRIMARY_BLUE, TEXT_LIGHT)

    # Registry Table
    draw.rounded_rectangle([24, 204, W - 24, 750], radius=12, fill=BG_CARD, outline=BORDER_COLOR, width=1)
    
    # Table Header
    draw.rounded_rectangle([24, 204, W - 24, 248], radius=12, fill=BG_CARD_SUBTLE)
    draw.rectangle([24, 230, W - 24, 248], fill=BG_CARD_SUBTLE)
    draw.text((44, 218), "ORGANISATION NAME", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.text((380, 218), "TOWN / CITY", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.text((580, 218), "COUNTY / REGION", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.text((780, 218), "TIER & ROUTE", fill=TEXT_MUTED, font=font(11, bold=True))
    draw.text((1050, 218), "VERIFIED JOBS", fill=TEXT_MUTED, font=font(11, bold=True))

    rows = [
        ("Deliveroo UK Limited", "London", "Greater London", "Skilled Worker (A-Rating)", "14 Open Roles"),
        ("Monzo Bank Limited", "London", "Greater London", "Skilled Worker (A-Rating)", "9 Open Roles"),
        ("Arm Limited", "Cambridge", "Cambridgeshire", "Skilled Worker (A-Rating)", "22 Open Roles"),
        ("Revolut Ltd", "London", "Greater London", "Skilled Worker (A-Rating)", "18 Open Roles"),
        ("Checkout Ltd", "London", "Greater London", "Skilled Worker (A-Rating)", "6 Open Roles"),
        ("Wise Payments Limited", "London", "Greater London", "Skilled Worker (A-Rating)", "11 Open Roles"),
        ("Amazon UK Services Ltd", "London", "Greater London", "Skilled Worker (A-Rating)", "84 Open Roles"),
        ("Skyscanner Limited", "Edinburgh", "Midlothian", "Skilled Worker (A-Rating)", "8 Open Roles")
    ]

    ry = 260
    for comp, city, county, route, open_jobs in rows:
        draw.line([24, ry + 44, W - 24, ry + 44], fill=BORDER_COLOR, width=1)
        draw.text((44, ry + 12), comp, fill=TEXT_TITLE, font=font(13, bold=True))
        draw.text((380, ry + 12), city, fill=TEXT_BODY, font=font(13))
        draw.text((580, ry + 12), county, fill=TEXT_MUTED, font=font(13))
        
        draw_pill(draw, [780, ry + 6, 980, ry + 36], route, SUCCESS_GREEN_BG, SUCCESS_GREEN)
        draw_pill(draw, [1050, ry + 6, 1180, ry + 36], open_jobs, PRIMARY_BLUE_BG, PRIMARY_BLUE)

        ry += 54

    out = ASSETS_DIR / "ui_feature_sponsor_directory.png"
    img.save(out)
    return str(out)

if __name__ == "__main__":
    print("[1/4] Generating UK Job Directory UI...")
    f1 = build_ui_job_directory()
    print("[2/4] Generating Application Tracker UI...")
    f2 = build_ui_applications_kanban()
    print("[3/4] Generating Autonomous Email Agent UI...")
    f3 = build_ui_email_agent()
    print("[4/4] Generating UK Sponsor Registry UI...")
    f4 = build_ui_sponsor_registry()
    print("All feature UI mockups generated successfully!")

