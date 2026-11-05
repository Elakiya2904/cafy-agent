"""Create a PDF overview of Cafy Agent architecture, features, and user interfaces.

Assembles project diagrams and explanatory sections into a shareable PDF report.
"""
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF

WORKSPACE_ROOT = Path(__file__).parent.resolve()
OUTPUT_PDF = WORKSPACE_ROOT / "cafy-agent-up-to-date-features-and-pipelines.pdf"
DIAGRAMS_DIR = WORKSPACE_ROOT / "doc_assets"
DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)

UI_EDITOR_PATH = Path(r"C:\Users\vlela\.gemini\antigravity\brain\75d067f9-1e31-4512-b557-ebd599b1d95c\ui_screenshot_editor.jpg")
UI_JOB_DIR_PATH = DIAGRAMS_DIR / "ui_feature_job_directory.png"
UI_APP_TRACKER_PATH = DIAGRAMS_DIR / "ui_feature_application_tracker.png"
UI_EMAIL_AGENT_PATH = DIAGRAMS_DIR / "ui_feature_email_agent.png"
UI_SPONSOR_DIR_PATH = DIAGRAMS_DIR / "ui_feature_sponsor_directory.png"
UI_CHATBOT_PATH = DIAGRAMS_DIR / "ui_feature_career_chatbot.png"

# Color scheme
C_NAVY = (15, 23, 42)
C_BLUE = (37, 99, 235)
C_CYAN = (6, 182, 212)
C_GREEN = (16, 185, 129)
C_GRAY_BG = (248, 250, 252)
C_CARD_BG = (255, 255, 255)
C_BORDER = (203, 213, 225)
C_TEXT = (30, 41, 59)
C_MUTED = (100, 116, 139)
C_WHITE = (255, 255, 255)

FONT_PATH = "C:/Windows/Fonts/arial.ttf"
FONT_BOLD_PATH = "C:/Windows/Fonts/arialbd.ttf"

def get_font(size, bold=False):
    p = FONT_BOLD_PATH if bold else FONT_PATH
    return ImageFont.truetype(p, size)

def draw_card(draw, box, title, lines, fill_color=C_CARD_BG, border_color=C_BORDER, header_color=C_BLUE):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle([x1, y1, x2, y2], radius=10, fill=fill_color, outline=border_color, width=2)
    draw.rounded_rectangle([x1, y1, x2, y1 + 32], radius=10, fill=header_color)
    draw.rectangle([x1, y1 + 20, x2, y1 + 32], fill=header_color)
    draw.text((x1 + 14, y1 + 6), title, fill=C_WHITE, font=get_font(14, bold=True))
    
    curr_y = y1 + 42
    for l in lines:
        draw.text((x1 + 14, curr_y), l, fill=C_TEXT, font=get_font(12))
        curr_y += 19

def draw_arrow(draw, start, end, color=C_BLUE, width=3):
    draw.line([start, end], fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if x2 > x1:
        draw.polygon([(x2, y2), (x2 - 10, y2 - 6), (x2 - 10, y2 + 6)], fill=color)
    elif x2 < x1:
        draw.polygon([(x2, y2), (x2 + 10, y2 - 6), (x2 + 10, y2 + 6)], fill=color)
    elif y2 > y1:
        draw.polygon([(x2, y2), (x2 - 6, y2 - 10), (x2 + 6, y2 - 10)], fill=color)
    elif y2 < y1:
        draw.polygon([(x2, y2), (x2 - 6, y2 + 10), (x2 + 6, y2 + 10)], fill=color)

def create_diag_overview():
    img = Image.new("RGB", (1000, 480), C_GRAY_BG)
    draw = ImageDraw.Draw(img)

    draw_card(draw, (40, 40, 280, 200), "Pipeline 1: Ingestion", [
        "• 8 ATS Platforms Polled",
        "• Strict UK Geofilter (UK Only)",
        "• Excludes Ireland & Foreign",
        "• UK Home Office Register"
    ], header_color=(30, 58, 138))

    draw_card(draw, (360, 40, 640, 200), "Pipeline 2: Resume & Match", [
        "• Structured 6-Section Parser",
        "• Internships & Single Dates",
        "• 100pt Profile Strength Meter",
        "• Anti-Hallucination Guardrail"
    ], header_color=C_BLUE)

    draw_card(draw, (720, 40, 960, 200), "Pipeline 3: Email Agent", [
        "• Secure IMAP / OAuth2 Polling",
        "• 6-Class Message Classifier",
        "• Automated Pipeline Advance",
        "• Cadence Follow-Up Engine"
    ], header_color=(15, 118, 110))

    draw_arrow(draw, (280, 120), (360, 120))
    draw_arrow(draw, (640, 120), (720, 120))

    draw_card(draw, (200, 270, 800, 440), "FastAPI Unified Application Gateway (backend/main.py)", [
        "• Persistence: Dual SQLite (local dev) / PostgreSQL",
        "• Inference: Groq LLM API with automated fallback (openai/gpt-oss-20b)",
        "• Document Engines: XeLaTeX (PDF) and python-docx (DOCX) rendering",
        "• Context Isolation: Multi-user thread-safe candidate session state"
    ], header_color=C_NAVY)

    draw_arrow(draw, (160, 200), (320, 270))
    draw_arrow(draw, (500, 200), (500, 270))
    draw_arrow(draw, (840, 200), (680, 270))

    p = DIAGRAMS_DIR / "diag_overview.png"
    img.save(p)
    return str(p)

class ComprehensiveDocPDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 8)
        self.set_text_color(100, 116, 139)
        self.cell(0, 8, "Cafy Agent - System Specifications & Client Overview", 0, 0, "L")
        self.cell(0, 8, "Official System Documentation", 0, 1, "R")
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.3)
        self.line(12, 16, 198, 16)
        self.ln(4)

    def footer(self):
        self.set_y(-12)
        self.set_font("Arial", "", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", 0, 0, "C")

    def section_heading(self, num, title):
        self.set_font("Arial", "B", 13)
        self.set_text_color(15, 23, 42)
        self.cell(0, 8, f"{num}. {title}", 0, 1, "L")
        self.set_draw_color(37, 99, 235)
        self.set_line_width(0.6)
        self.line(12, self.get_y(), 198, self.get_y())
        self.ln(3)

    def para(self, text):
        self.set_font("Arial", "", 9.5)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 5, text)
        self.ln(2)

def generate_pdf():
    print("[1/3] Generating system architecture diagrams...")
    d_over = create_diag_overview()

    print("[2/3] Preparing document layout with all feature UI screens...")
    pdf = ComprehensiveDocPDF(orientation="P", unit="mm", format="A4")
    pdf.alias_nb_pages()
    pdf.add_font("Arial", "", FONT_PATH)
    pdf.add_font("Arial", "B", FONT_BOLD_PATH)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(12, 14, 12)

    # ================= PAGE 1: EXECUTIVE ARCHITECTURE =================
    pdf.add_page()
    pdf.ln(2)
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(0, 10, "Cafy Agent - Enterprise Platform Specifications", 0, 1, "L")
    pdf.set_font("Arial", "B", 11)
    pdf.set_text_color(37, 99, 235)
    pdf.cell(0, 6, "Production Architecture, Autonomous Pipelines, and Complete UI Showcase", 0, 1, "L")
    pdf.ln(2)

    pdf.section_heading(1, "Executive System Architecture")
    pdf.para(
        "Cafy Agent is an enterprise-grade ATS automation and career intelligence platform designed for the UK market. "
        "Built on a high-throughput FastAPI backend and a responsive React Vite frontend, the system unifies three autonomous pipelines: "
        "Pipeline 1 continuously ingests and geofilters vacancies strictly within the United Kingdom; Pipeline 2 delivers structured resume parsing, "
        "100-point profile strength evaluation, hybrid job matching, and zero-hallucination AI resume tailoring; and Pipeline 3 operates an autonomous "
        "Email Agent that synchronizes recruiter correspondence and automates pipeline status transitions."
    )
    pdf.image(d_over, x=14, y=pdf.get_y() + 2, w=182)
    pdf.ln(92)

    pdf.section_heading(2, "Core Engineering Pillars")
    pdf.para(
        "• Strict UK Containment: Employs negative regex to reject overseas and Irish postings, coupled with positive matching for 25+ UK hubs.\n"
        "• Home Office Sponsorship Integration: Verifies employers against the UK Home Office Worker Register (Skilled Worker sponsor list).\n"
        "• Factual Invariance & Factual Guardrails: Prevents LLM hallucinations using strict token and metric verification.\n"
        "• Production Dual Compilers: Generates publication-grade XeLaTeX single-page PDFs and formatted Microsoft Word (.docx) files."
    )

    # ================= PAGE 2: FEATURE 1 - JOB DISCOVERY UI =================
    pdf.add_page()
    pdf.section_heading(3, "Feature 1: UK Job Discovery & Visa Sponsorship Search Engine")
    pdf.para(
        "The job discovery engine aggregates listings across 8 enterprise ATS systems (Greenhouse, Lever, Ashby, Workday, Workable, Oracle Cloud, "
        "BreezyHR, and Pinpoint). Workday network faceting filters foreign listings before download, while the normalizer strictly validates UK locations. "
        "Every role is cross-referenced against the UK Home Office Worker Register to badge licensed Skilled Worker sponsors."
    )
    if UI_JOB_DIR_PATH.is_file():
        pdf.image(str(UI_JOB_DIR_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(114)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• Municipal Corridor Filtering: Filter by London, Manchester, Edinburgh, Bristol, Cambridge, or UK-wide remote.\n"
        "• Immigration & Sponsorship Badges: Instantly isolate verified Skilled Worker visa sponsors from standard listings.\n"
        "• Normalized Compensation: All salaries standardized to annual GBP ranges with minimum threshold filters."
    )

    # ================= PAGE 3: FEATURE 2 - RESUME STUDIO UI =================
    pdf.add_page()
    pdf.section_heading(4, "Feature 2: Resume Studio, Match Scoring & Live PDF Workspace")
    pdf.para(
        "The Resume Studio provides structured 6-section profile extraction, real-time job match scoring, and instant XeLaTeX compilation. "
        "The parser seamlessly extracts single-term dates, date ranges, and internship experiences, crediting full experience to candidate profiles."
    )
    if UI_EDITOR_PATH.is_file():
        pdf.image(str(UI_EDITOR_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(90)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• Live Section Match Meters: Displays real-time fit across Professional Summary, Skills, Work History, Education, and Projects.\n"
        "• Factual Action Rewriting: Utilizes Groq LLM inference with automated fallback and zero-hallucination verification.\n"
        "• Instant Multi-Format Downloads: One-click export to publication-ready single-page PDF (XeLaTeX) and editable Word document (.docx)."
    )

    # ================= PAGE 4: FEATURE 3 - APPLICATION KANBAN UI =================
    pdf.add_page()
    pdf.section_heading(5, "Feature 3: Candidate Application Pipeline & Stage Management")
    pdf.para(
        "Candidates manage their active application funnel using an interactive, state-synchronized pipeline. Applications advance through stages "
        "(Applied -> Screening -> Assessment -> Interviewing -> Offer) via candidate actions or automated email notifications."
    )
    if UI_APP_TRACKER_PATH.is_file():
        pdf.image(str(UI_APP_TRACKER_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(114)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• Multi-Stage Lifecycle Board: Instant visibility into pending recruiter calls, technical assessments, and formal offers.\n"
        "• Deadline & Calendar Alerts: Extracts submission deadlines for take-home coding challenges with visual countdown badges.\n"
        "• Automated State Progression: Auto-promotes candidates to 'Interviewing' immediately upon receiving recruiter scheduling links."
    )

    # ================= PAGE 5: FEATURE 4 - EMAIL AGENT UI =================
    pdf.add_page()
    pdf.section_heading(6, "Feature 4: Autonomous Recruiter Email Agent & Follow-Up Hub")
    pdf.para(
        "Pipeline 3 connects candidate inboxes via secure IMAP or OAuth2 protocols. Recruiter emails and ATS notification relays (@greenhouse-mail.io, "
        "@ashbyhq.com) are classified by a 6-class neural categorizer, updating application states and pre-drafting professional responses."
    )
    if UI_EMAIL_AGENT_PATH.is_file():
        pdf.image(str(UI_EMAIL_AGENT_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(114)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• 6-Class Categorization Stream: Distinguishes Interview Invitations, Technical Assessments, Acknowledgments, Offers, and Rejections.\n"
        "• Human-in-the-Loop Approval: Pre-drafts context-aware acceptance and availability replies for one-click candidate review.\n"
        "• Follow-Up Cadence Automation: Detects applications with no recruiter reply after 7 to 10 business days and queues inquiry drafts."
    )

    # ================= PAGE 6: FEATURE 5 - UK SPONSOR DIRECTORY UI =================
    pdf.add_page()
    pdf.section_heading(7, "Feature 5: Official UK Home Office Licensed Sponsor Directory")
    pdf.para(
        "An authoritative directory of licensed UK employers authorised to sponsor international professionals under the Skilled Worker route. "
        "Cross-references the official UK Home Office Register of Licensed Sponsors with city and county verification."
    )
    if UI_SPONSOR_DIR_PATH.is_file():
        pdf.image(str(UI_SPONSOR_DIR_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(114)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• Live Register Search: Search by corporate legal entity, trading name, industry, or UK town/county.\n"
        "• Licensing Tier Verification: Highlights Skilled Worker (A-Rating), Global Business Mobility, and Scale-up routes.\n"
        "• Real-Time Vacancy Cross-Reference: Connects each licensed sponsor directly to live open vacancies discovered across ATS platforms."
    )

    # ================= PAGE 7: FEATURE 6 - CAREER CHATBOT & COPILOT UI =================
    pdf.add_page()
    pdf.section_heading(8, "Feature 6: Cafy Agent - AI Career Analyst & Copilot (Chatbot)")
    pdf.para(
        "An evidence-grounded conversational career analyst accessible through an interactive slide-out dock. Powered by Groq LLM inference, "
        "the chatbot analyzes candidate resume facts against active UK job listings to answer strategic application questions in real time."
    )
    if UI_CHATBOT_PATH.is_file():
        pdf.image(str(UI_CHATBOT_PATH), x=14, y=pdf.get_y() + 2, w=182)
        pdf.ln(114)

    pdf.para(
        "Key Interface Capabilities:\n"
        "• Strategic Application Prioritization: Recommends which UK roles to apply to first based on match score, recency, and sponsorship viability.\n"
        "• Match Fit Explanation: Granularly explains why a candidate received a 94% or 82% fit, isolating matched vs. missing technical skills.\n"
        "• Market-Driven Skill Gap Analysis: Highlights recurring missing competencies across current UK vacancies with high-ROI learning roadmaps.\n"
        "• Interactive In-Chat Job Cards: Renders real-time, clickable recommendation cards with direct 'Tailor Resume' action buttons.\n"
        "• Strict Zero-Hallucination Bound: Constrained to real database evidence; prohibited from inventing scores, employers, or qualifications."
    )

    pdf.output(str(OUTPUT_PDF))
    print(f"[3/3] Successfully compiled 7-page comprehensive client documentation PDF to: {OUTPUT_PDF}")

if __name__ == "__main__":
    generate_pdf()
