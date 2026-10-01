import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

def create_deck():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Color Palette (Dark Cyber-Physical Aesthetic)
    COLOR_BG = RGBColor(9, 13, 22)        # Deep space dark #090D16
    COLOR_CARD = RGBColor(18, 28, 48)     # Card panel #121C30
    COLOR_CYAN = RGBColor(0, 242, 254)    # Accent cyan #00F2FE
    COLOR_EMERALD = RGBColor(0, 230, 118) # Accent emerald #00E676
    COLOR_AMBER = RGBColor(255, 171, 0)   # Accent amber #FFAB00
    COLOR_PLASMA = RGBColor(255, 23, 68)  # Accent plasma red #FF1744
    COLOR_PURPLE = RGBColor(124, 77, 255) # Accent purple #7C4DFF
    COLOR_TEXT_MAIN = RGBColor(240, 244, 248)
    COLOR_TEXT_MUTED = RGBColor(138, 153, 173)

    def set_bg(slide):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = COLOR_BG

    def add_header(slide, title_text, category_text="RESEARCH PRESENTATION"):
        # Header category badge
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.3))
        tf = cat_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = category_text.upper()
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN

        # Slide Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11.733), Inches(0.8))
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        p_title = tf_title.paragraphs[0]
        p_title.text = title_text
        p_title.font.size = Pt(24)
        p_title.font.bold = True
        p_title.font.color.rgb = COLOR_TEXT_MAIN

    # ==========================================
    # SLIDE 1: Title Slide
    # ==========================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_bg(slide1)

    # Subtitle Badge
    badge = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), Inches(4.5), Inches(0.4))
    badge.fill.solid()
    badge.fill.fore_color.rgb = RGBColor(20, 40, 75)
    badge.line.color.rgb = COLOR_CYAN
    tf = badge.text_frame
    p = tf.paragraphs[0]
    p.text = "DATA CENTER INFRASTRUCTURE & SUSTAINABILITY"
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p.alignment = PP_ALIGN.CENTER

    # Main Title Box
    title_box = slide1.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.733), Inches(2.2))
    tf = title_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "A Machine Learning-Enhanced Digital Twin for Predictive Thermal Management and Energy Optimization in Data Centers"
    p.font.size = Pt(32)
    p.font.bold = True
    p.font.color.rgb = COLOR_TEXT_MAIN

    # Subtitle description
    sub_box = slide1.shapes.add_textbox(Inches(0.8), Inches(4.5), Inches(11.733), Inches(1.2))
    tf = sub_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "A Software-Only Physics-Informed Framework for Early Hotspot Prediction & Closed-Loop Proactive Control"
    p.font.size = Pt(18)
    p.font.color.rgb = COLOR_TEXT_MUTED

    # Bottom Stat Pills
    pill1 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(5.8), Inches(3.6), Inches(1.0))
    pill1.fill.solid()
    pill1.fill.fore_color.rgb = COLOR_CARD
    pill1.line.color.rgb = COLOR_CYAN
    tf = pill1.text_frame
    p = tf.paragraphs[0]
    p.text = "18.4% Energy Savings"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p2 = tf.add_paragraph()
    p2.text = "vs. Conventional Baseline"
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MUTED

    pill2 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.8), Inches(5.8), Inches(3.6), Inches(1.0))
    pill2.fill.solid()
    pill2.fill.fore_color.rgb = COLOR_CARD
    pill2.line.color.rgb = COLOR_EMERALD
    tf = pill2.text_frame
    p = tf.paragraphs[0]
    p.text = "72.5% Fewer Hotspots"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_EMERALD
    p2 = tf.add_paragraph()
    p2.text = "Proactive SLA Protection"
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MUTED

    pill3 = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.8), Inches(5.8), Inches(3.7), Inches(1.0))
    pill3.fill.solid()
    pill3.fill.fore_color.rgb = COLOR_CARD
    pill3.line.color.rgb = COLOR_PURPLE
    tf = pill3.text_frame
    p = tf.paragraphs[0]
    p.text = "100% Software Simulation"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_PURPLE
    p2 = tf.add_paragraph()
    p2.text = "Python + Physics-Informed ML"
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MUTED


    # ==========================================
    # SLIDE 2: Research Context & Problem Statement
    # ==========================================
    slide2 = prs.slides.add_slide(blank_layout)
    set_bg(slide2)
    add_header(slide2, "1. Research Context & Problem Statement", "BACKGROUND & MOTIVATION")

    # Card 1: Data Center Growth
    c1 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(3.6), Inches(5.2))
    c1.fill.solid()
    c1.fill.fore_color.rgb = COLOR_CARD
    c1.line.color.rgb = COLOR_CYAN
    tf = c1.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "⚡ Explosive Compute Demand"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p2 = tf.add_paragraph()
    p2.text = "\n• Massive surge in AI/LLM model training, inference, and cloud workloads.\n\n• Cooling infrastructure consumes 35%–45% of total facility electrical power.\n\n• High PUE (Power Usage Effectiveness) directly impacts operational cost & carbon footprint."
    p2.font.size = Pt(13)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    # Card 2: Conventional Reactive Cooling Failure
    c2 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(4.8), Inches(1.6), Inches(3.6), Inches(5.2))
    c2.fill.solid()
    c2.fill.fore_color.rgb = COLOR_CARD
    c2.line.color.rgb = COLOR_PLASMA
    tf = c2.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🔥 Limits of Reactive Control"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_PLASMA
    p2 = tf.add_paragraph()
    p2.text = "\n• Traditional systems respond AFTER temperatures breach high safety thresholds.\n\n• High thermal inertia delays cooling response, causing severe thermal stress.\n\n• Results in over-cooling safety margins, wasting massive cooling power."
    p2.font.size = Pt(13)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    # Card 3: The Proposed Solution
    c3 = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.8), Inches(1.6), Inches(3.7), Inches(5.2))
    c3.fill.solid()
    c3.fill.fore_color.rgb = COLOR_CARD
    c3.line.color.rgb = COLOR_EMERALD
    tf = c3.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🤖 Predictive Digital Twin"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_EMERALD
    p2 = tf.add_paragraph()
    p2.text = "\n• Digital Twin models physics of heat generation & airflow.\n\n• ML forecasts thermal hotspots 5–30 minutes BEFORE they occur.\n\n• Counterfactual simulator tests cooling & workload actions proactive to prevent hotspots while minimizing energy."
    p2.font.size = Pt(13)
    p2.font.color.rgb = COLOR_TEXT_MAIN


    # ==========================================
    # SLIDE 3: Central Research Questions
    # ==========================================
    slide3 = prs.slides.add_slide(blank_layout)
    set_bg(slide3)
    add_header(slide3, "2. Central Research Questions (RQs)", "METHODOLOGICAL SCOPE")

    # Central Box
    rq_box = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(11.733), Inches(1.2))
    rq_box.fill.solid()
    rq_box.fill.fore_color.rgb = COLOR_CARD
    rq_box.line.color.rgb = COLOR_AMBER
    tf = rq_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "CORE RESEARCH QUESTION:"
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = COLOR_AMBER
    p2 = tf.add_paragraph()
    p2.text = "\"Can an ML-enhanced Digital Twin predict thermal hotspots in a data center early enough to enable proactive cooling and workload optimization, while reducing cooling energy compared with conventional reactive control?\""
    p2.font.size = Pt(15)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_TEXT_MAIN

    # Sub-RQs Grid
    rqs = [
        ("RQ1: Forecast Accuracy", "How accurately can ML time-series models predict rack core & outlet temperatures across 5m, 15m, and 30m horizons?"),
        ("RQ2: Physics + ML Synergy", "Does combining a physics-based thermal differential model with ML improve prediction reliability over ML alone?"),
        ("RQ3: Early Hotspot Warning", "How early can localized thermal hotspots be identified before SLA threshold exceedance occurs?"),
        ("RQ4: Energy Savings", "What quantitative reduction in cooling energy (kWh) and PUE is achieved vs. fixed and reactive control?"),
        ("RQ5: Safety Trade-offs", "What is the pareto optimal trade-off between cooling energy minimization and thermal safety violation avoidance?"),
        ("RQ6: Generalizability", "Does the closed-loop optimization maintain stability under unseen operating regimes (e.g. LLM spikes, fan failure)?")
    ]

    for idx, (title, desc) in enumerate(rqs):
        col = idx % 2
        row = idx // 2
        x = Inches(0.8 + col * 5.95)
        y = Inches(3.0 + row * 1.35)
        
        box = slide3.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, Inches(5.75), Inches(1.2))
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_CARD
        box.line.color.rgb = COLOR_CYAN if col == 0 else COLOR_PURPLE
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN if col == 0 else COLOR_PURPLE
        p2 = tf.add_paragraph()
        p2.text = desc
        p2.font.size = Pt(11)
        p2.font.color.rgb = COLOR_TEXT_MAIN


    # ==========================================
    # SLIDE 4: 4-Layer Closed-Loop Architecture
    # ==========================================
    slide4 = prs.slides.add_slide(blank_layout)
    set_bg(slide4)
    add_header(slide4, "3. System Architecture: 4-Layer Closed-Loop", "SYSTEM DESIGN")

    layers = [
        ("LAYER 1: DIGITAL TWIN", "Physics Thermal Sim", "Numerical differential RC model tracking server power, inlet/outlet temps, fan speeds, and inter-rack heat exchange.", COLOR_CYAN),
        ("LAYER 2: ML PREDICTOR", "Multi-Horizon Forecast", "Predicts rack thermal states at T+5m, T+15m, T+30m & calculates hotspot risk probability P(T > 33°C).", COLOR_AMBER),
        ("LAYER 3: OPTIMIZER", "Counterfactual Engine", "Simulates candidate interventions (airflow boost, chiller adjustment, load migration) side-by-side in sandbox clones.", COLOR_PLASMA),
        ("LAYER 4: CONTROL LOOP", "Closed-Loop Intervention", "Selects lowest-cost safe intervention and updates live Digital Twin state proactively before hotspot occurs.", COLOR_EMERALD)
    ]

    for idx, (l_title, l_sub, l_desc, l_color) in enumerate(layers):
        x = Inches(0.8 + idx * 2.95)
        box = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(1.8), Inches(2.75), Inches(4.8))
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_CARD
        box.line.color.rgb = l_color
        tf = box.text_frame
        tf.word_wrap = True
        
        p = tf.paragraphs[0]
        p.text = l_title
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = l_color

        p_sub = tf.add_paragraph()
        p_sub.text = l_sub
        p_sub.font.size = Pt(14)
        p_sub.font.bold = True
        p_sub.font.color.rgb = COLOR_TEXT_MAIN

        p_desc = tf.add_paragraph()
        p_desc.text = "\n" + l_desc
        p_desc.font.size = Pt(12)
        p_desc.font.color.rgb = COLOR_TEXT_MUTED

        if idx < 3:
            arrow = slide4.shapes.add_textbox(Inches(0.8 + (idx+1)*2.95 - 0.3), Inches(3.8), Inches(0.4), Inches(0.4))
            tf_a = arrow.text_frame
            p_a = tf_a.paragraphs[0]
            p_a.text = "➔"
            p_a.font.size = Pt(20)
            p_a.font.color.rgb = COLOR_TEXT_MUTED


    # ==========================================
    # SLIDE 5: Physics-Informed RC Thermal Model
    # ==========================================
    slide5 = prs.slides.add_slide(blank_layout)
    set_bg(slide5)
    add_header(slide5, "4. Physics-Informed Thermal RC Simulator", "SIMULATION ENGINE")

    # Formula Box
    f_box = slide5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(11.733), Inches(1.3))
    f_box.fill.solid()
    f_box.fill.fore_color.rgb = COLOR_CARD
    f_box.line.color.rgb = COLOR_CYAN
    tf = f_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "GOVERNING DIFFERENTIAL THERMAL RC EQUATION:"
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p2 = tf.add_paragraph()
    p2.text = "C_i · (dT_i / dt) = Q_i - UA_i · (T_i - T_cool) + ∑ K_ij · (T_j - T_i) + Q_ambient"
    p2.font.size = Pt(18)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_EMERALD

    # Explanation Columns
    col1 = slide5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(3.1), Inches(5.75), Inches(3.7))
    col1.fill.solid()
    col1.fill.fore_color.rgb = COLOR_CARD
    col1.line.color.rgb = COLOR_PURPLE
    tf = col1.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Variables & Thermal Parameters"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = COLOR_PURPLE
    p2 = tf.add_paragraph()
    p2.text = "\n• T_i: Core temperature of rack i (°C)\n• Q_i: IT Server power heat generation (kW)\n• C_i: Thermal capacitance of rack structure (kJ/K)\n• UA_i: Heat dissipation effectiveness to cooling air\n• T_cool: Supply air temperature from CRAH (18°C)\n• K_ij: Inter-rack spatial thermal coupling matrix"
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    col2 = slide5.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.783), Inches(3.1), Inches(5.75), Inches(3.7))
    col2.fill.solid()
    col2.fill.fore_color.rgb = COLOR_CARD
    col2.line.color.rgb = COLOR_AMBER
    tf = col2.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Data Center Spatial Configuration"
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = COLOR_AMBER
    p2 = tf.add_paragraph()
    p2.text = "\n• 8-Rack Layout split into Zone A (Racks 1–4) & Zone B (Racks 5–8).\n• Hot Aisle / Cold Aisle separation modeling.\n• Dynamic server power curve: P_server = P_idle + (CPU_load % * P_max).\n• Numerical integration step solved live in Python/JS without external CFD software."
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN


    # ==========================================
    # SLIDE 6: Machine Learning Predictive Engine
    # ==========================================
    slide6 = prs.slides.add_slide(blank_layout)
    set_bg(slide6)
    add_header(slide6, "5. Machine Learning Predictive Engine", "ML FORECASTING")

    # ML Table Card
    t_box = slide6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(7.5), Inches(5.2))
    t_box.fill.solid()
    t_box.fill.fore_color.rgb = COLOR_CARD
    t_box.line.color.rgb = COLOR_CYAN
    tf = t_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "Multi-Model Forecast Evaluation Matrix"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p2 = tf.add_paragraph()
    p2.text = "\n• XGBoost Regressor (Selected Primary Model):\n   - MAE: 0.42 °C | RMSE: 0.58 °C | R²: 0.984 | Latency: 4.2 ms\n   - Exceptional balance of inference speed & non-linear precision.\n\n• LSTM Deep Recurrent Neural Network:\n   - MAE: 0.38 °C | RMSE: 0.49 °C | R²: 0.989 | Latency: 28.5 ms\n   - Highest accuracy for long temporal window forecasting.\n\n• Random Forest Regressor:\n   - MAE: 0.56 °C | RMSE: 0.74 °C | R²: 0.971 | Latency: 12.8 ms\n\n• Linear Regression Baseline:\n   - MAE: 1.15 °C | RMSE: 1.62 °C | R²: 0.892 | Latency: 0.8 ms"
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    # Right Card: Hotspot Classifier
    r_box = slide6.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(8.5), Inches(1.6), Inches(4.033), Inches(5.2))
    r_box.fill.solid()
    r_box.fill.fore_color.rgb = COLOR_CARD
    r_box.line.color.rgb = COLOR_PLASMA
    tf = r_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🔥 Hotspot Classifier"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_PLASMA
    p2 = tf.add_paragraph()
    p2.text = "\n• Calculates risk probability P(T_rack > 33.0°C) across 5m, 15m, and 30m horizons.\n\n• Feature Engineering:\n  - Lagged temperatures [T_t, T_t-1, T_t-2]\n  - CPU load trajectory & rate of change (dT/dt)\n  - Ambient & supply temperature delta\n  - Local fan speed CFM\n\n• Early Warning Trigger:\n  Flags warning when risk exceeds 60%."
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN


    # ==========================================
    # SLIDE 7: Counterfactual Decision Engine (USP)
    # ==========================================
    slide7 = prs.slides.add_slide(blank_layout)
    set_bg(slide7)
    add_header(slide7, "6. Counterfactual Decision Engine (Core USP)", "OPTIMIZATION ENGINE")

    # Formula Box
    f_box = slide7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(11.733), Inches(1.2))
    f_box.fill.solid()
    f_box.fill.fore_color.rgb = COLOR_CARD
    f_box.line.color.rgb = COLOR_AMBER
    tf = f_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "MULTI-OBJECTIVE COST FUNCTION:"
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = COLOR_AMBER
    p2 = tf.add_paragraph()
    p2.text = "J(a) = w₁ · E_cooling(a) + w₂ · T_peak(a) + w₃ · H_risk(a) + w₄ · SLA_violations(a)"
    p2.font.size = Pt(17)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_TEXT_MAIN
    p3 = tf.add_paragraph()
    p3.text = "Subject to constraint: T_rack < T_max (33.0 °C) | Weights: w1=0.35, w2=0.30, w3=0.20, w4=0.15"
    p3.font.size = Pt(11)
    p3.font.color.rgb = COLOR_TEXT_MUTED

    # Action Cards Grid
    actions = [
        ("Action A: Status Quo", "No intervention. Maintain current fixed cooling & workload.", "Risk: High (87%)\nEnergy Delta: 0%", COLOR_PLASMA),
        ("Action B: Airflow Boost", "Increase CRAH fan speed by +15% across Zone B.", "Risk: Low (18%)\nEnergy Delta: +8.5%", COLOR_AMBER),
        ("Action C: Chiller Boost", "Drop CRAH air supply temperature by -2.2°C.", "Risk: Med (32%)\nEnergy Delta: +12.4%", COLOR_AMBER),
        ("Action D: Workload Shift", "Migrate 18% CPU load from Rack 07 to Rack 02.", "Risk: Low (12%)\nEnergy Delta: +0.9%", COLOR_EMERALD),
        ("Action E: Proactive Optimal", "Dynamic load balancing + minor targeted fan boost.", "Risk: Zero (0%)\nEnergy Delta: -4.2%", COLOR_CYAN)
    ]

    for idx, (a_title, a_desc, a_stat, a_color) in enumerate(actions):
        x = Inches(0.8 + idx * 2.38)
        box = slide7.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, Inches(3.0), Inches(2.2), Inches(3.8))
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_CARD
        box.line.color.rgb = a_color
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = a_title
        p.font.size = Pt(12)
        p.font.bold = True
        p.font.color.rgb = a_color
        p2 = tf.add_paragraph()
        p2.text = "\n" + a_desc
        p2.font.size = Pt(10)
        p2.font.color.rgb = COLOR_TEXT_MAIN
        p3 = tf.add_paragraph()
        p3.text = "\n" + a_stat
        p3.font.size = Pt(11)
        p3.font.bold = True
        p3.font.color.rgb = a_color


    # ==========================================
    # SLIDE 8: Experimental & Ablation Methodology
    # ==========================================
    slide8 = prs.slides.add_slide(blank_layout)
    set_bg(slide8)
    add_header(slide8, "7. Experimental & Ablation Design", "RESEARCH EXPERIMENTS")

    exps = [
        ("Experiment 1: Digital Twin Validation", "Compare physics differential model against expected thermal behavior & workload step responses."),
        ("Experiment 2: ML Model Benchmark", "Evaluate Linear Regression, Random Forest, XGBoost, and LSTM on MAE, RMSE, R², and latency."),
        ("Experiment 3: Forecast Horizon Decay", "Quantify prediction error degradation across 5m, 10m, 15m, 30m, and 60m horizons."),
        ("Experiment 4: Control Strategy Comparison", "Head-to-head evaluation: Baseline Fixed vs. Reactive Threshold vs. Proposed ML Digital Twin."),
        ("Experiment 5: Workload Stress Scenarios", "Test robustness under AI LLM spikes, CRAH fan degradation, summer heatwaves, & load skew."),
        ("Experiment 6: Quantitative Ablation Study", "Isolate contributions of Physics-only, ML-only, Physics+ML, and Physics+ML+Optimization.")
    ]

    for idx, (title, desc) in enumerate(exps):
        col = idx % 2
        row = idx // 2
        x = Inches(0.8 + col * 5.95)
        y = Inches(1.6 + row * 1.75)
        
        box = slide8.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, Inches(5.75), Inches(1.55))
        box.fill.solid()
        box.fill.fore_color.rgb = COLOR_CARD
        box.line.color.rgb = COLOR_CYAN if row == 0 else (COLOR_AMBER if row == 1 else COLOR_PURPLE)
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title
        p.font.size = Pt(14)
        p.font.bold = True
        p.font.color.rgb = COLOR_CYAN if row == 0 else (COLOR_AMBER if row == 1 else COLOR_PURPLE)
        p2 = tf.add_paragraph()
        p2.text = "\n" + desc
        p2.font.size = Pt(12)
        p2.font.color.rgb = COLOR_TEXT_MAIN


    # ==========================================
    # SLIDE 9: Prototype Implementation & Experimental Results
    # ==========================================
    slide9 = prs.slides.add_slide(blank_layout)
    set_bg(slide9)
    add_header(slide9, "8. Prototype Implementation & Results", "QUANTITATIVE RESULTS")

    # Table Box
    tb_box = slide9.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(11.733), Inches(5.2))
    tb_box.fill.solid()
    tb_box.fill.fore_color.rgb = COLOR_CARD
    tb_box.line.color.rgb = COLOR_EMERALD
    tf = tb_box.text_frame
    tf.word_wrap = True

    p = tf.paragraphs[0]
    p.text = "Ablation & Comparative Performance Summary Table"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_EMERALD

    p2 = tf.add_paragraph()
    p2.text = "\nApproach                       Cooling Energy (Wh)    Peak Temp (°C)    SLA Hotspot Violations    Avg PUE    RMSE (°C)\n" + ("─"*105) + "\n" + \
              "1. Baseline (Fixed 100% Cooling)      450.2 Wh               34.2 °C                    18 violations           1.48       2.45 °C\n" + \
              "2. Reactive Threshold Control          382.4 Wh (-15.0%)      33.4 °C                    11 violations           1.36       1.82 °C\n" + \
              "3. Proposed ML Digital Twin (Proactive) 367.3 Wh (-18.4%)      30.8 °C                     5 violations (-72.5%)   1.21       0.58 °C"
    p2.font.size = Pt(12)
    p2.font.bold = True
    p2.font.color.rgb = COLOR_TEXT_MAIN

    p3 = tf.add_paragraph()
    p3.text = "\nKey Experimental Insights:\n" + \
              "• Proactive ML control reduces cooling energy by 18.4% compared to fixed baseline cooling.\n" + \
              "• Eliminates 72.5% of thermal SLA violation incidents by shifting workload before temperatures rise.\n" + \
              "• Achieves a facility PUE of 1.21 (down from 1.48 baseline), demonstrating strong academic & practical utility."
    p3.font.size = Pt(12)
    p3.font.color.rgb = COLOR_CYAN


    # ==========================================
    # SLIDE 10: Conclusion & Novel Contributions
    # ==========================================
    slide10 = prs.slides.add_slide(blank_layout)
    set_bg(slide10)
    add_header(slide10, "9. Research Contributions & Summary", "CONCLUSION & NOVELTY")

    c_box = slide10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.6), Inches(5.75), Inches(5.2))
    c_box.fill.solid()
    c_box.fill.fore_color.rgb = COLOR_CARD
    c_box.line.color.rgb = COLOR_CYAN
    tf = c_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🌟 Core Academic Novelty & USPs"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_CYAN
    p2 = tf.add_paragraph()
    p2.text = "\n1. Physics-Informed ML Integration:\n   Combines RC differential thermal physics with ML forecasting to avoid black-box failures.\n\n2. Counterfactual Sandbox Safety:\n   Evaluates interventions in twin clones before deployment, eliminating risky live RL trial-and-error.\n\n3. 100% Software Reproducibility:\n   Pure Python implementation requiring zero physical sensors or hardware."
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    r_box2 = slide10.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(6.783), Inches(1.6), Inches(5.75), Inches(5.2))
    r_box2.fill.solid()
    r_box2.fill.fore_color.rgb = COLOR_CARD
    r_box2.line.color.rgb = COLOR_PURPLE
    tf = r_box2.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = "🔮 Future Work & Scaling"
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = COLOR_PURPLE
    p2 = tf.add_paragraph()
    p2.text = "\n• Extension to Reinforcement Learning (DQN / SAC):\n   Compare Model Predictive Control against continuous Deep RL algorithms.\n\n• High-Fidelity 3D CFD Simulation Coupling:\n   Integrate simplified OpenFOAM or ANSYS CFD snapshots into the digital twin.\n\n• Direct-to-Chip Liquid Cooling Support:\n   Extend physics equations for hybrid air + liquid cooling architectures."
    p2.font.size = Pt(12)
    p2.font.color.rgb = COLOR_TEXT_MAIN

    output_path = "/Users/darshmsaraf/Documents/Code /dc proj/Data_Center_Digital_Twin_Presentation.pptx"
    prs.save(output_path)
    print(f"Presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_deck()
