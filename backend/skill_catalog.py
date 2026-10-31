"""Profession catalog: skills and job titles for every field Cafy supports.

Engineering/software skills stay in ``resume_service.SKILL_TAXONOMY``; this module adds the
other professions. Each domain lists its skills and its roles. A role maps to the job-title
phrases employers use for it, which drives both résumé role detection and job-title matching.
"""
from __future__ import annotations

import re
from typing import Dict, List

# domain -> {"skills": [...], "roles": {role title: [title phrases used in job postings]}}
DOMAINS: Dict[str, Dict] = {
    "Sales & Business Development": {
        "skills": [
            "Sales", "Business Development", "Lead Generation", "Prospecting", "Cold Calling",
            "Cold Outreach", "Outbound Sales", "Inbound Sales", "B2B Sales", "B2B", "B2C", "SaaS",
            "Account Management", "Key Account Management", "Pipeline Management", "Sales Pipeline",
            "Sales Forecasting", "Quota Attainment", "Closing Deals", "Deal Closing", "Negotiation",
            "Customer Acquisition", "Customer Retention", "Customer Relationship Management",
            "Relationship Management", "Client Relationship", "Solution Selling", "Consultative Selling",
            "Product Demonstration", "Product Presentation", "Market Research", "Competitive Analysis",
            "Upselling", "Cross-selling", "Lead Qualification", "Territory Management", "Salesforce",
            "HubSpot", "CRM", "Salesloft", "Apollo", "LinkedIn Sales Navigator", "Sales Navigator",
            "ZoomInfo", "Pre-Sales", "Presales", "Sales Enablement", "Sales Operations",
            "Revenue Growth", "Client Communication",
        ],
        "roles": {
            "Sales Executive": ["sales executive", "sales representative", "sales associate", "inside sales", "sales manager"],
            "Account Executive": ["account executive"],
            "Business Development Representative": ["business development", "bdr", "sdr", "sales development"],
            "Account Manager": ["account manager"],
            "Solutions Consultant": ["solutions consultant", "solutions engineer", "sales engineer", "pre-sales", "presales"],
        },
    },
    "Customer Success & Support": {
        "skills": [
            "Customer Success", "Customer Support", "Customer Service", "Technical Support", "Help Desk",
            "Ticket Management", "Zendesk", "Intercom", "Freshdesk", "Onboarding", "Churn Reduction",
            "Escalation Management", "SLA Management", "Live Chat", "Call Center", "Conflict Resolution",
            "Customer Satisfaction", "CSAT", "NPS", "Troubleshooting",
        ],
        "roles": {
            "Customer Success Manager": ["customer success", "client success", "outcomes architect", "onboarding specialist"],
            "Customer Support Specialist": ["customer support", "customer service", "support specialist", "support representative", "support agent", "help desk"],
            "Technical Support Engineer": ["technical support", "support engineer"],
        },
    },
    "Teaching & Education": {
        "skills": [
            "Lesson Planning", "Curriculum Development", "Curriculum Design", "Classroom Management",
            "Differentiated Instruction", "Student Assessment", "Assessment Design", "Teaching",
            "Tutoring", "Mentoring", "Special Education", "IEP", "Early Childhood Education",
            "Instructional Design", "E-Learning", "Learning Management System", "Moodle", "Canvas LMS",
            "Blackboard", "Google Classroom", "Parent Communication", "Student Engagement",
            "Educational Technology", "STEM Education", "Phonics", "Behavior Management",
            "Academic Advising", "Course Design", "Learning & Development", "Training Delivery",
            "Public Speaking", "TEFL", "TESOL", "Montessori",
        ],
        "roles": {
            "Teacher": ["teacher", "teaching assistant", "classroom teacher", "lecturer", "instructor"],
            "Tutor": ["tutor"],
            "Instructional Designer": ["instructional designer", "learning designer", "curriculum developer", "learning experience"],
            "Trainer": ["trainer", "learning and development", "learning & development", "enablement"],
            "Education Counselor": ["school counselor", "education counsellor", "academic advisor", "admissions"],
        },
    },
    "Accounting": {
        "skills": [
            "Accounting", "Bookkeeping", "Accounts Payable", "Accounts Receivable", "General Ledger",
            "Bank Reconciliation", "Month-End Close", "Financial Reporting", "Financial Statements",
            "Payroll", "Tax Preparation", "Taxation", "VAT", "GST", "IFRS", "GAAP", "Auditing",
            "Internal Audit", "Internal Controls", "Reconciliation", "Journal Entries", "Invoicing",
            "QuickBooks", "Xero", "Tally", "SAP", "SAP FICO", "NetSuite", "Sage", "Oracle Financials",
            "Cost Accounting", "Fixed Assets", "Accruals", "Expense Management", "Compliance",
            "Variance Analysis", "Chartered Accountant", "CPA", "ACCA", "CMA",
        ],
        "roles": {
            "Accountant": ["accountant", "accounting", "bookkeeper", "ledger"],
            "Accounts Payable Specialist": ["accounts payable", "ap specialist", "accounts receivable", "ar specialist"],
            "Auditor": ["auditor", "audit associate", "internal audit"],
            "Tax Specialist": ["tax accountant", "tax specialist", "tax analyst", "tax associate"],
            "Payroll Specialist": ["payroll"],
        },
    },
    "Finance": {
        "skills": [
            "Financial Analysis", "Financial Modeling", "Financial Modelling", "FP&A", "Budgeting",
            "Forecasting", "Valuation", "DCF", "Investment Banking", "Equity Research", "Portfolio Management",
            "Risk Management", "Credit Analysis", "Treasury", "Corporate Finance", "Mergers & Acquisitions",
            "M&A", "Private Equity", "Venture Capital", "Capital Markets", "Derivatives", "Bloomberg",
            "Financial Planning", "Cash Flow Management", "Revenue Recognition", "Anti-Money Laundering",
            "AML", "KYC", "Fintech", "Banking", "Wealth Management", "Underwriting", "Actuarial",
            "CFA", "Business Analysis", "Unit Economics", "Pricing",
        ],
        "roles": {
            "Financial Analyst": ["financial analyst", "finance analyst", "fp&a", "finance associate", "finance manager"],
            "Investment Analyst": ["investment analyst", "investment associate", "equity research", "investment banking", "private equity"],
            "Risk Analyst": ["risk analyst", "credit analyst", "risk manager", "compliance analyst", "aml analyst", "kyc analyst"],
            "Treasury Analyst": ["treasury"],
            "Controller": ["controller", "financial controller", "finance director"],
        },
    },
    "Hardware & Electronics Engineering": {
        "skills": [
            "Embedded Systems", "Embedded C", "Firmware", "RTOS", "Microcontrollers", "ARM Cortex",
            "STM32", "Arduino", "Raspberry Pi", "PCB Design", "Altium Designer", "KiCad", "Eagle",
            "Cadence", "OrCAD", "Analog Circuit Design", "Digital Circuit Design", "Circuit Design",
            "VLSI", "Verilog", "VHDL", "SystemVerilog", "FPGA", "ASIC", "RTL Design", "Signal Processing",
            "Oscilloscope", "Schematic Capture", "Power Electronics", "RF Design", "Antenna Design",
            "SPICE", "LTspice", "Hardware Testing", "Hardware Debugging", "Board Bring-up", "IoT",
            "I2C", "SPI", "UART", "CAN Bus", "PLC", "SCADA", "Semiconductor", "Design Verification",
            "DFM", "EMC", "Signal Integrity", "MATLAB", "Simulink",
        ],
        "roles": {
            "Hardware Engineer": ["hardware engineer", "hardware design", "electronics engineer", "electrical engineer", "board design"],
            "Embedded Engineer": ["embedded", "firmware"],
            "VLSI Engineer": ["vlsi", "asic", "fpga", "rtl", "design verification", "silicon"],
            "RF Engineer": ["rf engineer", "antenna", "wireless hardware"],
            "Test Engineer": ["test engineer", "validation engineer", "hardware test"],
        },
    },
    "Mechanical & Manufacturing Engineering": {
        "skills": [
            "SolidWorks", "AutoCAD", "CATIA", "Creo", "Pro/E", "Siemens NX", "Fusion 360", "Inventor",
            "ANSYS", "FEA", "Finite Element Analysis", "CFD", "Computational Fluid Dynamics", "GD&T",
            "Thermodynamics", "Fluid Mechanics", "Heat Transfer", "Mechanical Design", "Product Design",
            "3D Printing", "CNC", "CNC Machining", "Machining", "Sheet Metal", "Welding", "Injection Molding",
            "Design for Manufacturing", "Manufacturing Processes", "Lean Manufacturing", "Six Sigma", "Kaizen",
            "5S", "Root Cause Analysis", "FMEA", "Quality Control", "Quality Assurance", "ISO 9001",
            "HVAC", "Piping", "Robotics", "Industrial Automation", "Mechatronics", "Prototyping", "Technical Drawing",
            "Bill of Materials", "BOM", "PLM", "Process Engineering", "Maintenance Engineering",
        ],
        "roles": {
            "Mechanical Engineer": ["mechanical engineer", "mechanical design", "design engineer", "cad engineer"],
            "Manufacturing Engineer": ["manufacturing engineer", "production engineer", "process engineer", "industrial engineer"],
            "Quality Engineer": ["quality engineer", "quality assurance engineer", "quality inspector", "quality manager"],
            "Robotics Engineer": ["robotics engineer", "automation engineer", "mechatronics"],
            "Maintenance Engineer": ["maintenance engineer", "reliability engineer", "field service engineer"],
        },
    },
    "Civil & Construction": {
        "skills": [
            "Structural Analysis", "Structural Design", "STAAD Pro", "ETABS", "Revit", "BIM", "Primavera",
            "MS Project", "Site Supervision", "Site Engineering", "Quantity Surveying", "Estimating",
            "Construction Management", "Surveying", "Geotechnical Engineering", "Highway Engineering",
            "Water Resources", "Concrete Design", "Building Codes", "Project Scheduling", "Cost Estimation",
            "Health and Safety", "OSHA", "Contract Administration", "Civil 3D",
        ],
        "roles": {
            "Civil Engineer": ["civil engineer", "structural engineer", "site engineer", "geotechnical"],
            "Construction Manager": ["construction manager", "project engineer", "site manager", "construction project"],
            "Quantity Surveyor": ["quantity surveyor", "cost estimator", "estimator"],
        },
    },
    "Healthcare & Nursing": {
        "skills": [
            "Patient Care", "Nursing", "Clinical Assessment", "Medication Administration", "Vital Signs",
            "Electronic Health Records", "EHR", "Epic", "Cerner", "Triage", "Phlebotomy", "CPR", "BLS", "ACLS",
            "Infection Control", "Wound Care", "Patient Education", "Care Planning", "Medical Terminology",
            "HIPAA", "Clinical Trials", "Pharmacy", "Medical Coding", "ICD-10", "Public Health",
            "Physiotherapy", "Occupational Therapy", "Mental Health", "Pharmacology", "Medical Billing",
            "Laboratory Testing", "Diagnostics", "Radiology", "Emergency Care",
        ],
        "roles": {
            "Nurse": ["nurse", "registered nurse", "nursing", "healthcare assistant"],
            "Clinical Research Associate": ["clinical research", "clinical trial"],
            "Pharmacist": ["pharmacist", "pharmacy technician"],
            "Medical Coder": ["medical coder", "medical biller", "medical billing", "health information"],
            "Therapist": ["therapist", "physiotherapist", "counsellor", "counselor"],
        },
    },
    "Human Resources & Recruiting": {
        "skills": [
            "Recruitment", "Talent Acquisition", "Sourcing", "Interviewing", "Applicant Tracking System", "ATS",
            "Workday HCM", "BambooHR", "Greenhouse", "Lever", "Employee Relations", "Onboarding", "Performance Management",
            "Compensation and Benefits", "Payroll Administration", "HR Policies", "HRIS", "Employer Branding",
            "Employee Engagement", "Learning and Development", "Labour Law", "Employment Law", "Workforce Planning",
            "Diversity and Inclusion", "Offboarding", "Succession Planning",
        ],
        "roles": {
            "Recruiter": ["recruiter", "talent acquisition", "sourcer", "recruiting coordinator", "talent partner"],
            "HR Generalist": ["hr generalist", "human resources", "hr business partner", "hr manager", "people partner", "people operations", "people ops", "hr coordinator", "hr assistant"],
        },
    },
    "Marketing & Communications": {
        "skills": [
            "Digital Marketing", "Content Marketing", "Content Writing", "Copywriting", "SEO", "SEM", "PPC",
            "Google Ads", "Facebook Ads", "Meta Ads", "Google Analytics", "Email Marketing", "Mailchimp", "Marketo",
            "Marketing Automation", "Social Media Marketing", "Social Media Management", "Brand Management",
            "Brand Strategy", "Product Marketing", "Growth Marketing", "Performance Marketing", "Influencer Marketing",
            "Public Relations", "Event Management", "Campaign Management", "Market Segmentation", "Marketing Analytics",
            "Content Strategy", "Video Editing", "Community Management", "Storytelling", "A/B Testing", "Demand Generation",
            "Account-Based Marketing", "ABM", "Press Releases", "Editing", "Proofreading", "Technical Writing",
        ],
        "roles": {
            "Marketing Specialist": ["marketing manager", "marketing specialist", "marketing executive", "marketing associate", "marketing coordinator", "growth marketing", "demand generation", "performance marketing"],
            "Content Writer": ["content writer", "copywriter", "content marketing", "content strategist", "editor", "technical writer"],
            "Social Media Manager": ["social media", "community manager"],
            "Product Marketing Manager": ["product marketing"],
            "PR Specialist": ["public relations", "communications manager", "communications specialist", "pr manager"],
        },
    },
    "Design & Creative": {
        "skills": [
            "Graphic Design", "UI Design", "UX Design", "User Research", "Wireframing", "Prototyping",
            "Adobe Photoshop", "Photoshop", "Adobe Illustrator", "Illustrator", "Adobe InDesign", "InDesign",
            "Adobe XD", "After Effects", "Premiere Pro", "Sketch", "Figma", "Canva", "Motion Graphics",
            "Typography", "Branding", "Visual Design", "Interaction Design", "Design Systems", "Usability Testing",
            "Information Architecture", "Illustration", "Video Production", "Photography", "3D Modeling",
            "Blender", "Maya", "Animation", "Art Direction",
        ],
        "roles": {
            "Product Designer": ["product designer", "ux designer", "ui designer", "ui/ux", "ux researcher", "user experience", "interaction designer"],
            "Graphic Designer": ["graphic designer", "visual designer", "brand designer", "creative designer", "art director", "illustrator"],
            "Motion Designer": ["motion designer", "video editor", "animator", "videographer"],
        },
    },
    "Operations & Supply Chain": {
        "skills": [
            "Supply Chain Management", "Logistics", "Procurement", "Purchasing", "Vendor Management",
            "Inventory Management", "Warehouse Management", "Demand Planning", "Supply Planning", "Forecasting",
            "Operations Management", "Process Improvement", "Order Management", "Freight", "Shipping",
            "Import Export", "Customs", "Fleet Management", "Distribution", "ERP", "SAP MM", "Oracle SCM",
            "Supplier Negotiation", "Sourcing", "Production Planning", "Capacity Planning", "KPI Tracking",
            "Cost Reduction", "Business Operations", "Strategy & Operations", "Retail Operations", "Facilities Management",
        ],
        "roles": {
            "Operations Manager": ["operations manager", "operations analyst", "operations associate", "operations coordinator", "business operations", "bizops", "strategy and operations", "operations specialist"],
            "Supply Chain Analyst": ["supply chain", "logistics", "demand planner", "supply planner", "inventory", "warehouse"],
            "Procurement Specialist": ["procurement", "purchasing", "buyer", "sourcing manager", "category manager"],
        },
    },
    "Product & Project Management": {
        "skills": [
            "Product Management", "Product Strategy", "Roadmapping", "Product Roadmap", "Backlog Management",
            "User Stories", "Stakeholder Management", "Project Management", "Program Management", "Project Planning",
            "Risk Management", "Resource Planning", "Budget Management", "PMP", "PRINCE2", "Kanban", "Waterfall",
            "OKRs", "Go-to-Market", "Requirements Gathering", "Business Analysis", "Asana", "Trello", "Monday.com",
            "Confluence", "Change Management", "Cross-functional Collaboration", "Vendor Coordination", "Status Reporting",
        ],
        "roles": {
            "Product Manager": ["product manager", "product owner", "associate product manager", "technical product"],
            "Project Manager": ["project manager", "project coordinator", "program manager", "delivery manager", "scrum master", "project management"],
            "Business Analyst": ["business analyst", "systems analyst", "requirements analyst", "product analyst"],
        },
    },
    "Legal & Compliance": {
        "skills": [
            "Contract Drafting", "Contract Review", "Contract Negotiation", "Legal Research", "Legal Writing",
            "Corporate Law", "Intellectual Property", "Litigation", "Regulatory Compliance", "Data Privacy", "GDPR",
            "Due Diligence", "Case Management", "Paralegal", "Employment Law", "Commercial Law", "Compliance Monitoring",
            "Policy Development", "Risk Assessment", "Trade Compliance", "Legal Operations",
        ],
        "roles": {
            "Legal Counsel": ["legal counsel", "lawyer", "solicitor", "attorney", "associate general counsel", "general counsel"],
            "Paralegal": ["paralegal", "legal assistant", "legal operations", "legal coordinator"],
            "Compliance Officer": ["compliance officer", "compliance manager", "privacy", "regulatory affairs"],
        },
    },
    "Administration & Office": {
        "skills": [
            "Administration", "Office Management", "Calendar Management", "Scheduling", "Data Entry",
            "Records Management", "Executive Support", "Travel Coordination", "Event Coordination", "Reception",
            "Document Management", "Microsoft Office", "MS Office", "Microsoft Word", "Microsoft Outlook",
            "Google Workspace", "Typing", "Filing", "Meeting Coordination", "Expense Reporting", "Minute Taking",
            "Front Desk", "Office Administration",
        ],
        "roles": {
            "Administrative Assistant": ["administrative assistant", "office administrator", "office manager", "executive assistant", "personal assistant", "receptionist", "office coordinator", "admin assistant", "data entry"],
        },
    },
    "Data & Analytics": {
        "skills": [
            "Data Analysis", "Data Analytics", "Data Visualization", "Business Intelligence", "Power BI", "Tableau",
            "Looker", "Excel", "Microsoft Excel", "Google Sheets", "Statistics", "Statistical Analysis",
            "A/B Testing", "Dashboarding", "KPI Reporting", "Reporting", "SPSS", "SAS", "Data Modeling",
            "Data Cleaning", "Data Warehousing", "Market Research", "Survey Design", "Pivot Tables", "VLOOKUP",
            "Excel Macros", "VBA", "Qlik", "Metabase",
        ],
        "roles": {
            "Data Analyst": ["data analyst", "business intelligence", "bi analyst", "reporting analyst", "analytics analyst", "insights analyst", "research analyst", "analytics manager"],
        },
    },
    "Business & Productivity Tools": {
        "skills": [
            "PowerPoint", "Microsoft PowerPoint", "Notion", "Slack", "Google Slides", "Zoom", "Microsoft Teams",
        ],
        "roles": {},
    },
}

# Soft skills read from résumé text; only counted as skills, never used for role detection.
GENERAL_SKILLS: List[str] = [
    "Communication", "Leadership", "Teamwork", "Problem Solving", "Critical Thinking", "Time Management",
    "Adaptability", "Presentation Skills", "Stakeholder Management", "Mentoring", "Customer Focus",
    "Attention to Detail", "Analytical Skills", "Research", "Collaboration",
]

# Skills too common in job text to prove a match (they appear in nearly every posting).
WEAK_MATCH_SKILLS = {s.lower() for s in GENERAL_SKILLS} | {
    "analysis", "research", "demonstration", "persuasion", "reporting", "administration",
}

# Extra skill aliases (lowercase -> canonical)
ALIASES: Dict[str, str] = {
    "ms excel": "Excel", "microsoft excel": "Excel", "ms powerpoint": "PowerPoint",
    "microsoft powerpoint": "PowerPoint", "crm": "CRM", "bd": "Business Development",
    "biz dev": "Business Development", "b2b sales": "B2B Sales", "cold-calling": "Cold Calling",
    "pre sales": "Pre-Sales", "sales navigator": "LinkedIn Sales Navigator",
    "cross selling": "Cross-selling", "up-selling": "Upselling", "upselling": "Upselling",
    "financial modelling": "Financial Modeling", "ms office": "Microsoft Office",
    "solidworks": "SolidWorks", "ui/ux": "UX Design",
}


def domain_skill_taxonomy() -> Dict[str, List[str]]:
    """Category name -> skills, for merging into the résumé skill taxonomy."""
    return {name: list(dict.fromkeys(d["skills"])) for name, d in DOMAINS.items()}


def all_roles() -> Dict[str, List[str]]:
    """Role title -> title phrases, across every domain."""
    out: Dict[str, List[str]] = {}
    for d in DOMAINS.values():
        for role, phrases in d["roles"].items():
            out[role] = phrases
    return out


def title_has_phrase(title: str, phrase: str) -> bool:
    return re.search(r"(?<![a-z0-9])" + re.escape(phrase.lower()) + r"(?![a-z0-9])", title.lower()) is not None


def role_matches_title(role: str, title: str) -> bool:
    """True when a job title is a posting for the given target role (catalog phrases first)."""
    phrases = all_roles().get(role) or []
    return any(title_has_phrase(title, p) for p in phrases) or title_has_phrase(title, role)


# Alternative wordings employers and candidates use for the same skill (lowercase skill -> phrases).
SYNONYMS: Dict[str, List[str]] = {
    "lesson planning": ["lesson plans", "planning lessons", "scheme of work", "schemes of work", "teaching plans"],
    "classroom management": ["behaviour management in class", "managing a classroom", "class management"],
    "student assessment": ["assessing pupils", "pupil assessment", "marking and assessment", "assessment of learners"],
    "curriculum development": ["curriculum planning", "curriculum design", "developing curricula"],
    "teaching": ["teach", "instruct pupils", "deliver lessons", "classroom instruction"],
    "patient care": ["care of patients", "patient-centred care", "patient centered care", "caring for patients", "direct patient care"],
    "medication administration": ["administering medication", "administer medicines", "drug administration", "medicines management"],
    "electronic health records": ["ehr", "electronic patient records", "emr", "electronic medical records"],
    "infection control": ["infection prevention", "ipc", "infection prevention and control"],
    "accounts payable": ["payables", "ap processing", "supplier payments", "purchase ledger"],
    "accounts receivable": ["receivables", "ar processing", "sales ledger", "credit control"],
    "general ledger": ["gl", "nominal ledger", "general ledger accounting"],
    "month-end close": ["month end close", "month-end", "month end", "period end close", "monthly close"],
    "bank reconciliation": ["bank recs", "reconciling bank", "bank reconciliations"],
    "financial reporting": ["management accounts", "statutory accounts", "financial statements preparation"],
    "financial modeling": ["financial models", "three statement model", "3-statement model", "building models"],
    "financial analysis": ["analysing financial", "analyzing financial", "financial analytics"],
    "fp&a": ["financial planning and analysis", "financial planning & analysis"],
    "budgeting": ["budget preparation", "budget management", "budget planning", "managing budgets"],
    "customer support": ["customer care", "client support", "customer assistance", "customer queries"],
    "customer service": ["client service", "customer care", "customer-facing"],
    "customer success": ["client success", "account success", "customer onboarding and retention"],
    "lead generation": ["generating leads", "lead gen", "generate leads", "pipeline generation"],
    "business development": ["biz dev", "new business", "growing new accounts", "business growth"],
    "negotiation": ["negotiating", "negotiate contracts", "commercial negotiation"],
    "recruitment": ["recruiting", "talent sourcing", "hiring", "candidate sourcing"],
    "talent acquisition": ["recruiting", "recruitment"],
    "employee relations": ["er cases", "employee relations casework", "staff relations"],
    "project management": ["managing projects", "project delivery", "project planning and delivery"],
    "stakeholder management": ["managing stakeholders", "stakeholder engagement", "stakeholder communication"],
    "social media marketing": ["social media campaigns", "social media strategy", "social channels"],
    "content writing": ["writing content", "content creation", "copy writing"],
    
    "seo": ["search engine optimisation", "search engine optimization"],
    "supply chain management": ["supply chain", "supply-chain"],
    "inventory management": ["stock control", "stock management", "inventory control"],
    "procurement": ["purchasing", "sourcing and procurement", "buying"],
    "embedded systems": ["embedded software", "embedded development", "embedded firmware"],
    "pcb design": ["printed circuit board", "pcb layout", "board layout", "schematic and layout"],
    "circuit design": ["circuit development", "designing circuits", "electronic design"],
    "mechanical design": ["mechanical engineering design", "designing mechanical", "product design engineering"],
    "solidworks": ["solid works", "3d cad"],
    "autocad": ["auto cad", "2d cad"],
    "quality assurance": ["qa", "quality management", "quality system"],
    "health and safety": ["h&s", "health & safety", "ehs", "workplace safety"],
    "project scheduling": ["programme management", "construction scheduling", "planning and scheduling"],
    "contract drafting": ["drafting contracts", "contract preparation"],
    "regulatory compliance": ["regulatory requirements", "compliance with regulations", "regulatory affairs"],
    "data analysis": ["analysing data", "analyzing data", "data analytics", "data-driven analysis"],
    "data visualization": ["data visualisation", "dashboards", "visualising data"],
    "administration": ["administrative support", "admin support", "office administration"],
    "calendar management": ["diary management", "managing calendars", "scheduling meetings"],
    "excel": ["spreadsheets", "ms excel", "microsoft excel"],
    "powerpoint": ["presentations", "ms powerpoint", "microsoft powerpoint"],
}
