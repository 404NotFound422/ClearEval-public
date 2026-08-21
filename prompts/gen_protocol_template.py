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
3.  **Justify Choices:** Briefly explain *why* you selected this specific clearing method and labeling strategy. Highlight the advantages for the given Problem Statement.
4.  **Generate Protocol:** Create a detailed, step-by-step protocol based on your chosen method and labeling, strictly adhering to the formatting requirements below.

**Formatting Requirements for the Protocol Section:**
*   The output should start with your chosen method, labeling, and justification.
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
*   Ensure the protocol is complete from standard tissue preparation (assume PFA fixation unless otherwise indicated) through to refractive index matching suitable for the likely imaging method (assume light-sheet or confocal based on context).
*   Be specific with parameters (concentrations, times, temperatures). Use standard abbreviations (RT, ℃, vol/vol, wt/vol).
*   The sequence of steps must be logical and scientifically sound for your **chosen** clearing method.
*   Your **chosen** labeling strategy must be integrated logically within the protocol. Provide reasonable parameters for the labeling step itself (e.g., antibody concentration, incubation time/temp, washing steps).
*   Generate *only* the Chosen Method, Chosen Labeling, Justification, and the formatted Protocol Steps. Do not add extra introductory/concluding remarks.
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

**Chosen Method:** MACS
**Chosen Labeling:** [PI, CD31+Alexa Fluor 647] # means you choose PI and CD31+Alexa Fluor 647 as your labeling strategy, if you choose more dyes, please add them to the list.
**Justification:** iDISCO+ provides good clearing for whole mouse brains, excellent fluorescence preservation (especially for robust reporters like mCherry), and uses relatively common reagents. The methanol-based approach is generally faster than aqueous methods like CUBIC. Labeling relies on the existing endogenous signal, simplifying the process.

**Protocol Steps:**
1 Tissue Optical Clearing
1.1 Incubation with MACS-R0 (20 vol% MXDA, 15% w/v sorbitol, RI = 1.40) (Temperature: RT, Time: 36 hours)
1.2 Incubation with MACS-R1 (40 vol% MXDA, 30% w/v sorbitol in PBS, RI = 1.48) (Temperature: RT, Time: 12 hours)
1.3 Incubation with MACS-R2 (40 vol% MXDA, 50% w/v sorbitol, RI = 1.51) (Temperature: RT, Time: 12 hours)

**### End of Example ###**
---

Now, based on the `Problem Statement`, perform the task following all instructions and the example format.

"""