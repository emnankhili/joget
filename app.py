import os
import re
import json
import pdfplumber
import pytesseract
import subprocess
from flask import Flask, request, jsonify
from docx import Document
from openai import OpenAI
from werkzeug.utils import secure_filename

# === Config initiale ===
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
TEMP_FOLDER = os.path.join(BASE_DIR, "temp")
RESULTS_FOLDER = os.path.join(BASE_DIR, "results")
EXTRACTION_JSON = os.path.join(RESULTS_FOLDER, "extraction.json")
RESULTS_JSON = os.path.join(RESULTS_FOLDER, "results.json")
ALLOWED_EXTENSIONS = {"pdf", "docx"}
MODEL = "qwen/qwen3-32b"

client = OpenAI(
    api_key="",
    base_url="https://api.groq.com/openai/v1"
)

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(TEMP_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def append_to_json_array(filepath, new_data):
    data = []
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []
    # Supprime les anciennes entrées du même fichier
    data = [entry for entry in data if entry.get("fichier") != new_data.get("fichier")]
    data.append(new_data)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def load_json_data(filepath):
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []

def convert_docx_to_pdf(docx_path):
    try:
        subprocess.run(
            ["soffice", "--headless", "--convert-to", "pdf", "--outdir", TEMP_FOLDER, docx_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        pdf_filename = os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
        pdf_path = os.path.join(TEMP_FOLDER, pdf_filename)
        return pdf_path if os.path.exists(pdf_path) else None
    except subprocess.CalledProcessError as e:
        print(f"Erreur conversion docx: {e.stderr.decode()}")
        return None

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                content = page.extract_text()
                if content and len(content.strip()) > 30:
                    text += content + "\n"
                else:
                    image = page.to_image(resolution=300).original
                    text += pytesseract.image_to_string(image, lang="eng+fra") + "\n"
    except Exception as e:
        print(f"Erreur extraction PDF: {e}")
    return text.strip()

def clean_text_before_chunking(text):
    lines = text.splitlines()
    cleaned = []
    for line in lines:
        if re.search(r'^(t[eé]l|tel|email|adresse|mobile|phone)\s*:?', line.strip(), re.IGNORECASE):
            continue
        if len(line.strip()) <= 2:
            continue
        cleaned.append(line.strip())
    return "\n".join(cleaned)

def chunk_text(text, max_chars=2000):
    return [text[i:i + max_chars] for i in range(0, len(text), max_chars)]

def estimate_experience(from_year, to_year=2025):
    try:
        return max(0, to_year - int(from_year))
    except:
        return 0

def ask_groq(prompt):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Groq API error: {e}")
        return ""

def extract_from_chunk(chunk):
    prompt = f"""
Tu es un expert en ressources humaines.
Analyse le texte suivant, un extrait de CV, et renvoie UNIQUEMENT ce JSON strictement valide :

====================
{chunk}
====================

{{
    "nom_complet": "",
    "domaine_expertise": "",
    "date_diplome_principal": "",
    "annees_experience": 0,
    "nationalite": "",
    "diplomes": []
}}
🧠 Règles :
- Le "nom_complet" doit être extrait même s'il est mentionné comme "Nom de l'expert" ou "nom".
- Si le diplôme principal n’est pas de niveau Master ou Ingénieur, tu peux exceptionnellement prendre une "License" si c’est le diplôme le plus élevé.
- Si la date de diplôme n’est pas explicitement mentionnée, tu peux la **déduire** à partir des années de début de carrière professionnelle (première mission ou emploi).
- Le champ "domaine_expertise" doit résumer les compétences techniques/professionnelles évoquées dans le texte.
- Si plusieurs diplômes sont mentionnés, ajoute-les tous dans "diplomes".
- "nationalite" peut être déduite à partir des mots comme "Nationalité : Tunisienne" ou bien par sens et le pays de diplome de baccalauriat.
- Ne fais aucun commentaire.
- Tous les champs doivent être renseignés si possible.
- "date_diplome_principal" doit correspondre au diplôme de niveau ingénieur ou master (ignore les licences ou formations courtes).
- "annees_experience" doit être calculé à partir de "date_diplome_principal" ou bien a partir de la premiere annee ou il a entammer son cursus professionnel.
- "diplomes" doit contenir une liste de diplômes mentionnés dans le texte (diplome ,diplome obtenu...).
-le nom complet peut etre precede par non de l'expert et il est obligatoire de l'extraire ya pas un cv sans nom de l'expert .
⚠️ Ne fais AUCUN commentaire.
⚠️ Ne renvoie QUE le JSON (aucun préfixe ni suffixe, aucune phrase).
⚠️ S’il manque des données, laisse les valeurs vides ou à 0.
"""
    response = ask_groq(prompt)
    try:
        json_match = re.search(r'\{[\s\S]*?\}', response)
        if not json_match:
            return {}
        data = json.loads(json_match.group())
        if "date_diplome_principal" in data:
            year_match = re.search(r"\b(19|20)\d{2}\b", data["date_diplome_principal"])
            if year_match:
                data["date_diplome_principal"] = year_match.group()
                data["annees_experience"] = estimate_experience(data["date_diplome_principal"])
        return data
    except Exception as e:
        print(f"Erreur extraction JSON: {e}")
        return {}

def extract_data_from_text(text):
    cleaned = clean_text_before_chunking(text)
    chunks = chunk_text(cleaned)
    final = {
        "nom_complet": "",
        "domaine_expertise": "",
        "date_diplome_principal": "",
        "annees_experience": 0,
        "nationalite": "",
        "diplomes": []
    }
    for chunk in chunks:
        result = extract_from_chunk(chunk)
        for key in final:
            if key == "diplomes":
                final[key].extend(result.get(key, []))
            elif not final[key] and result.get(key):
                final[key] = result[key]
    final["diplomes"] = list(set(filter(None, final["diplomes"])))
    return final

# === ROUTES API ===
@app.route("/api/upload_and_analyse", methods=["POST"])
def upload_and_analyse():
    if "cv" not in request.files:
        return jsonify({"error": "Aucun fichier envoyé avec la clé 'cv'"}), 400

    file = request.files["cv"]

    if file.filename == "":
        return jsonify({"error": "Nom de fichier vide"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Extension non autorisée. Fichiers autorisés : PDF, DOCX"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    # Appelle analyse_fichier après upload
    if filename.lower().endswith(".pdf"):
        texte = extract_text_from_pdf(filepath)
    elif filename.lower().endswith(".docx"):
        pdf_path = convert_docx_to_pdf(filepath)
        if not pdf_path:
            return jsonify({"error": "Échec de conversion du DOCX en PDF"}), 500
        texte = extract_text_from_pdf(pdf_path)
    else:
        return jsonify({"error": "Extension non reconnue"}), 400

    if not texte.strip():
        return jsonify({"error": "Impossible d'extraire le texte du fichier"}), 500

    append_to_json_array(EXTRACTION_JSON, {"fichier": filename, "texte_complet": texte})
    data = extract_data_from_text(texte)
    data["fichier"] = filename
    append_to_json_array(RESULTS_JSON, data)

    return jsonify(data)

@app.route("/api/ask_from_file", methods=["POST"])
def api_ask_from_file():
    req = request.json
    fichier = req.get("fichier", "")
    question = req.get("question", "")

    if not fichier or not question:
        return jsonify({"error": "Le champ 'fichier' ou 'question' est manquant"}), 400

    # Chercher le texte dans extraction.json
    all_texts = load_json_data(EXTRACTION_JSON)
    match = next((item for item in all_texts if item.get("fichier") == fichier), None)

    if not match:
        return jsonify({"error": f"Aucun texte trouvé pour le fichier {fichier}"}), 404

    cv_text = match.get("texte_complet", "")
    if not cv_text.strip():
        return jsonify({"error": "Texte vide pour ce fichier"}), 400

    # Traitement par chunks
    for chunk in chunk_text(cv_text):
        prompt = f"""Réponds brièvement à la question suivante concernant ce CV :

➡️ {question}

Voici un extrait du CV :
=====================
{chunk}
=====================

Réponse brève, sans raisonnement ni analyse, uniquement une réponse directe :"""

        rep = ask_groq(prompt)
        if rep and len(rep.strip()) > 2:
            return jsonify({
                "fichier": fichier,
                "question": question,
                "reponse": rep.strip()
            })

    return jsonify({"reponse": "Aucune réponse trouvée"}), 200



@app.route("/api/query", methods=["POST"])
def api_query():
    req = request.json
    action = req.get("Action", "").strip()

    resumes = load_json_data(RESULTS_JSON)
    textes = load_json_data(EXTRACTION_JSON)
    by_file = {r["fichier"]: r for r in resumes}

    if action == "Get All":
        return jsonify(resumes)

    elif action == "Search":
        keywords = req.get("Keywords", "").lower()
        results = []
        if not keywords:
            return jsonify({"error": "Le champ 'Keywords' est requis pour l'action 'Search'"}), 400

        for txt in textes:
            if keywords in txt.get("texte_complet", "").lower():
                f = txt["fichier"]
                info = by_file.get(f, {})
                results.append({**info, "texte_complet": txt["texte_complet"]})
        return jsonify(results)

    elif action == "Filter":
        nom = req.get("nom", "").lower()
        domaine = req.get("domaine", "").lower()
        results = []

        for r in resumes:
            if (not nom or nom in r.get("nom_complet", "").lower()) and \
               (not domaine or domaine in r.get("domaine_expertise", "").lower()):
                results.append(r)
        return jsonify(results)

    else:
        return jsonify({"error": "Action inconnue. Utilisez 'Get All', 'Search', ou 'Filter'."}), 400

if __name__ == "__main__":
    app.run(debug=True)
