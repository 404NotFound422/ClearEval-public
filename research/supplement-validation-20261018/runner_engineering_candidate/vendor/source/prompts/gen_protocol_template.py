TEST_MODEL_GENERATION_PROMPT = """You are an expert research assistant specializing in tissue optical clearing techniques.
Your task is to generate a detailed, step-by-step protocol for the following specific problem statement:

**Problem Statement:**
[specific_question]

**restrctions**
You need to choose only ONE clearing method and several Dyes from the following lists:
{{restrictions}}


**Your Task Steps:**
1.  **Analyze:** Carefully read and understand the goals, tissue type, target structures, and any constraints mentioned in the **Problem Statement**.
2.  **Choose Method & Labeling:** Select the most suitable tissue clearing method (e.g., iDISCO+, CUBIC, uDISCO, CLARITY, PACT, etc.) and the best labeling strategy/dye(s) (e.g., specific antibody, fluorescent protein, chemical dye like PI/DAPI, lectin) to achieve the stated goals.. Consider factors like tissue size, fluorescence preservation, speed, or other factors implicitly suggested or commonly associated with the goal.
3.  **Respect the Output Contract:** Follow the output requirements in the Problem Statement. Do not add a separate justification section when only the first-line selection and subsequent steps are requested.
4.  **Generate Protocol:** Create a detailed, step-by-step protocol based on your chosen method and labeling, strictly adhering to the formatting requirements below.

**Formatting Requirements for the Protocol Section:**
*   The first line must state the selected labeling strategy and clearing method together, as requested by the Problem Statement. Do not output a separate justification section.
*   The protocol itself MUST follow this specific hierarchical format precisely:
    1.  Use numbered main steps (e.g., `1 Dehydration`, `2 Wash`, `3 Delipidation`).
    2.  Use numbered sub-steps within each main step (e.g., `1.1`, `1.2`, `2.1`).
    3.  For each sub-step, provide a clear description of the action, including:
        *   The primary reagent(s) used, including concentration if applicable (e.g., `Incubation with 20% (vol/vol) methanol aqueous solution`).
        *   The incubation temperature (e.g., `Temperature: RT` or `Temperature: 4 ℃`).
        *   The incubation time (e.g., `Time: 1 hour` or `Time: 12 hours`).
        *   Include these parameters directly within the sub-step description.

**Example Sub-step Format:**
`1.1 Incubation with 20% (vol/vol) methanol aqueous solution for 1 hour.(Temperature: RT, Time: 1 hours)`
`5.1 Incubation with chilled fresh 5% H2O2 in methanol (1 volume 30% H2O2 to 5 volumes MeOH).(Temperature: 4 ℃, Time: 12 hours)`
`12.1 Incubation with 100% (vol/vol) DBE (DBE, Sigma 108014-1KG) without shaking.(Temperature: 4 ℃, Time: 3 hours)`

**Protocol Generation Guidelines:**
*   Ensure the protocol directly addresses the **Problem Statement**.
*   Begin from the initial state explicitly stated in the Problem Statement. Treat stages explicitly completed and quality-controlled as givens, not required new actions. Do not infer an unspecified identity, completion status, or quality-control result. Cover only the remaining requested work.
*   Be specific with parameters (concentrations, times, temperatures). Use standard abbreviations (RT, ℃, vol/vol, wt/vol).
*   The sequence of steps must be logical and scientifically sound for your **chosen** clearing method.
*   The output scope explicitly requested in the Problem Statement takes precedence over general protocol-completeness guidance. Selecting a labeling strategy does not by itself request labeling procedures. If output is limited to clearing, RI matching, and storage/pre-imaging steps, state the selected labeling strategy on the first line but omit labeling incubation and labeling-wash procedures. If only labeling selection is requested, do not add procedural steps. Omission because of output scope does not mean labeling has already been completed; do not assert completion unless the Problem Statement explicitly states it. When labeling procedures are within the requested output scope and remain to be performed (including an explicitly requested full immunolabeling-and-clearing protocol), integrate them logically and provide reasonable parameters (e.g., antibody concentration, incubation time/temp, washing steps).
*   Generate *only* the first-line labeling and method selection followed by the formatted steps requested in the Problem Statement. Keep numbered main-step titles and substeps. Do not add separate selection, justification, or Protocol Steps sections, or introductory/concluding remarks.
---
**### 1-Shot Example ###**

**Example Problem Statement:**
I need to perform rapid optical clearing on a whole mouse brain labeled with PI. Please generate a detailed, parameter‑specified protocol to guide me through this experiment.

**restrictions**
You need to choose only ONE clearing method and several Dyes from the following lists:
ClearingMethod:{{iDISCO+, CUBIC, uDISCO, FDISCO, SOLID, MACS, CLARITY}}
Dye:{{SYTO, PI, DAPI, FITC , Alexa Fluor 647, DiI}}
Marker:{{c-fos, NeuN, GFAP, Iba1, CD31, MAP2}}

**Example Output:**

**Chosen Labeling:** [PI]; **Chosen Method:** MACS
1 Tissue Optical Clearing
1.1 Incubation with MACS-R0 (20 vol% MXDA, 15% w/v sorbitol, RI = 1.40) (Temperature: RT, Time: 36 hours)
1.2 Incubation with MACS-R1 (40 vol% MXDA, 30% w/v sorbitol in PBS, RI = 1.48) (Temperature: RT, Time: 12 hours)
1.3 Incubation with MACS-R2 (40 vol% MXDA, 50% w/v sorbitol, RI = 1.51) (Temperature: RT, Time: 12 hours)

**### End of Example ###**
---

Now, based on the `Problem Statement`, perform the task following all instructions and the example format.

"""