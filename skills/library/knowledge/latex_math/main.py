# Copyright (c) 2024-2026 JARVIS Project
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import re
from skills.utils import success_response, error_response

GREEK = {
    "alpha": "\u03b1", "beta": "\u03b2", "gamma": "\u03b3", "delta": "\u03b4",
    "epsilon": "\u03b5", "zeta": "\u03b6", "eta": "\u03b7", "theta": "\u03b8",
    "iota": "\u03b9", "kappa": "\u03ba", "lambda": "\u03bb", "mu": "\u03bc",
    "nu": "\u03bd", "xi": "\u03be", "omicron": "\u03bf", "pi": "\u03c0",
    "rho": "\u03c1", "sigma": "\u03c3", "tau": "\u03c4", "upsilon": "\u03c5",
    "phi": "\u03c6", "chi": "\u03c7", "psi": "\u03c8", "omega": "\u03c9",
    "Alpha": "\u0391", "Beta": "\u0392", "Gamma": "\u0393", "Delta": "\u0394",
    "Theta": "\u0398", "Lambda": "\u039b", "Pi": "\u03a0", "Sigma": "\u03a3",
    "Phi": "\u03a6", "Psi": "\u03a8", "Omega": "\u03a9",
}

LATEX_GREEK = {v: f"\\{k}" if k[0].islower() else f"\\{k}" for k, v in GREEK.items()}

LATEX_TO_TEXT = {
    r"\\frac{([^}]*)}{([^}]*)}": r"\1/\2",
    r"\\int": "integral of",
    r"\\sum": "sum of",
    r"\\prod": "product of",
    r"\\infty": "infinity",
    r"\\partial": "partial derivative",
    r"\\nabla": "nabla",
    r"\\rightarrow": "->",
    r"\\Rightarrow": "=>",
    r"\\leftarrow": "<-",
    r"\\Leftarrow": "<=",
    r"\\leftrightarrow": "<->",
    r"\\approx": "approximately",
    r"\\neq": "!=",
    r"\\leq": "<=",
    r"\\geq": ">=",
    r"\\times": "*",
    r"\\div": "/",
    r"\\cdot": "*",
    r"\\pm": "+/-",
    r"\\sqrt{([^}]*)}": "sqrt(\1)",
    r"\\sqrt\\[([^}]*)\\]{([^}]*)}": "\1-th root of \2",
    r"_{([^}]*)}": "_{_SUB_\1_}",
    r"\\{": "{",
    r"\\}": "}",
    r"\\text{([^}]*)}": "\1",
    r"\\sin": "sin",
    r"\\cos": "cos",
    r"\\tan": "tan",
    r"\\log": "log",
    r"\\ln": "ln",
    r"\\lim": "limit",
}

TEXT_TO_LATEX = {
    r"(?i)\bintegral\b": "\\int ",
    r"(?i)\bsum\b": "\\sum ",
    r"(?i)\bproduct\b": "\\prod ",
    r"(?i)\binfinity\b": "\\infty",
    r"(?i)\bpartial\b": "\\partial ",
    r"(?i)\bsqrt\b": "\\sqrt{...}",
    r"(?i)\bdelta\b": "\\delta ",
    r"(?i)\btheta\b": "\\theta ",
    r"(?i)\blambda\b": "\\lambda ",
    r"(?i)\bpi\b": "\\pi ",
    r"(?i)\bsigma\b": "\\sigma ",
    r"(?i)\bomega\b": "\\omega ",
    r"(?i)\balpha\b": "\\alpha ",
    r"(?i)\bbeta\b": "\\beta ",
    r"(?i)\bgamma\b": "\\gamma ",
    r"(?i)\bphi\b": "\\phi ",
    r"(\d+)\s*/\s*(\d+)": r"\\frac{\1}{\2}",
    r"->": "\\rightarrow ",
    r"=>": "\\Rightarrow ",
    r"~=": "\\approx ",
    r"!=": "\\neq ",
    r"<=": "\\leq ",
    r">=": "\\geq ",
    r"\*\*": "\\cdot ",
}

def latex_to_text(latex: str) -> str:
    text = latex
    for greek_char, greek_name in LATEX_GREEK.items():
        text = text.replace(greek_name, greek_char)
    for pattern, replacement in LATEX_TO_TEXT.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r"\^{([^}]*)}", "^(\1)", text)
    text = text.replace("_{_SUB_", "_").replace("_}", "")
    text = re.sub(r"\\([a-zA-Z]+)", r"\1", text).strip()
    text = re.sub(r"\s+", " ", text)
    return text

def text_to_latex(text: str) -> str:
    latex = text
    for pattern, replacement in TEXT_TO_LATEX.items():
        latex = re.sub(pattern, replacement, latex)
    for greek_char, greek_name in LATEX_GREEK.items():
        latex = latex.replace(greek_char, greek_name)
    latex = re.sub(r"\s+", " ", latex).strip()
    return latex

SUPPORTED_DESCRIPTION = (
    "Supports: fractions (a/b), integrals (\\int), sums (\\sum), "
    "Greek letters (alpha, beta, ...), trigonometric functions (sin, cos, tan), "
    "operators (+, -, *, /, <=, >=, !=, ->, =>), sqrt, subscripts, superscripts."
)

async def latex_math(params: dict) -> dict:
    action = params.get("action", "").strip().lower()
    input_str = params.get("input", "").strip()

    if not input_str:
        return error_response("Please provide an 'input' string.")

    if action == "latex-to-text":
        result = latex_to_text(input_str)
        return success_response({
            "action": "latex-to-text",
            "input": input_str,
            "output": result,
            "note": SUPPORTED_DESCRIPTION
        })

    elif action == "text-to-latex":
        result = text_to_latex(input_str)
        return success_response({
            "action": "text-to-latex",
            "input": input_str,
            "output": result,
            "note": SUPPORTED_DESCRIPTION
        })

    else:
        return error_response("Action must be 'latex-to-text' or 'text-to-latex'.")

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
