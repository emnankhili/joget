Pipeline complet et détaillé pour ton projet d’analyse de CV
1. Structure de dossiers et fichiers
plaintextCopierModifierton-projet-cv/
│
├── app.py                      # Ton fichier principal Flask (celui que tu m'as envoyé)
│
├── uploads/                    # Dossier où les CV uploadés seront stockés temporairement
│   └── (fichiers PDF/DOCX)     # Ex: cv1.pdf, candidature.docx
│
├── temp/                       # Dossier temporaire pour conversion DOCX -> PDF
│   └── (PDF générés ici)
│
├── results/                    # Résultats de l'analyse et textes extraits au format JSON
│   ├── extraction.json         # Texte extrait complet de chaque CV (liste JSON)
│   └── results.json            # Résultats d’analyse (nom, domaine, diplômes, etc)
│
├── requirements.txt            # Liste des packages Python à installer
│
├── README.md                   # Documentation de ton projet (optionnel)
2. Description des fichiers principaux
app.py : ton application Flask avec toutes les routes et la logique d’analyse.
uploads/ : stockage temporaire des CV uploadés par les utilisateurs.
temp/ : fichiers PDF temporaires générés après conversion DOCX->PDF.
results/extraction.json : JSON avec les textes complets extraits des CV.
results/results.json : JSON avec les données structurées extraites (nom, diplômes, etc).
3. Préparation de l’environnement
Fichier requirements.txt (à créer) :
plaintextCopierModifierFlask
pdfplumber
pytesseract
python-docx
openai
werkzeug
Remarque :
pytesseract nécessite que Tesseract OCR soit installé sur ta machine (programme externe).
soffice (LibreOffice) doit être installé sur la machine pour convertir DOCX en PDF via ligne de commande.
4. Détails du pipeline du code
Étape 1 : Upload du fichier CV
Endpoint : /api/upload_and_analyse (méthode POST)
Le client (ex: interface web, postman, Joget) envoie un fichier PDF ou DOCX sous la clé cv.
Le fichier est sauvegardé dans le dossier uploads/.
Étape 2 : Extraction du texte
Si fichier .pdf : texte extrait directement via pdfplumber.
Si fichier .docx : conversion en PDF dans temp/ via LibreOffice en ligne de commande, puis extraction PDF.
Si extraction texte échoue → erreur 500 retournée.
Étape 3 : Nettoyage du texte
Suppression des lignes contenant téléphone, email, etc.
Suppression des lignes trop courtes (<= 2 caractères).
Étape 4 : Découpage du texte en chunks (morceaux)
Découpe du texte en morceaux de 2000 caractères max pour le prompt.
Étape 5 : Analyse par chunks via modèle AI (Groq/OpenAI)
Pour chaque chunk, tu envoies un prompt personnalisé à l’API OpenAI Groq.
Extraction d’un JSON strict contenant nom, domaine, diplômes, etc.
Regroupement des résultats dans un seul JSON final par CV.
Étape 6 : Sauvegarde des données
Texte complet brut sauvegardé dans results/extraction.json (tableau JSON, une entrée par fichier).
Données analysées sauvegardées dans results/results.json (tableau JSON, une entrée par fichier).
Étape 7 : Réponse API
L’API renvoie le JSON d’analyse complet au client.
5. Autres fonctionnalités API
/api/ask_from_file : poser une question précise sur un CV déjà uploadé, via chunks.
/api/query :
"Get All" → renvoie tous les résultats analysés.
"Search" → recherche mots clés dans textes extraits.
"Filter" → filtre sur nom ou domaine d’expertise.
6. Détails techniques importants
Conversion DOCX → PDF utilise LibreOffice en mode headless, vérifie bien que la commande soffice est accessible dans ton PATH.
OCR via pytesseract pour pages sans texte extractible.
Gestion JSON : écriture en tableau JSON, suppression d’entrée précédente avec même nom de fichier pour mise à jour.
Sécurité : secure_filename protège le nommage fichier uploadé.
Dossier results : fichiers JSON persistants, ce qui permet de faire des recherches sans retraiter les fichiers.
API en debug mode (à changer en production).
7. Commandes utiles pour lancer le projet
bashCopierModifier# Installer les dépendances Pythonpip install -r requirements.txt
# Installer Tesseract (Linux exemple)sudo apt-get install tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng
# Installer LibreOffice (Linux exemple)sudo apt-get install libreoffice
# Lancer l’application Flaskpython app.py
8. Exemple de requête POST upload (via curl)
bashCopierModifiercurl -X POST http://localhost:5000/api/upload_and_analyse \
  -F "cv=@/chemin/vers/ton_cv.pdf" 
9. Exemple minimal de extraction.json (après plusieurs CV)
jsonCopierModifier[{"fichier": "cv1.pdf","texte_complet": "Nom: John Doe\nDiplôme: Master informatique 2015\n..."},{"fichier": "candidat.docx","texte_complet": "Nom: Jane Smith\nDiplôme: Ingénieur en électronique 2017\n..."} ] 
10. Exemple minimal de results.json
jsonCopierModifier[{"fichier": "cv1.pdf","nom_complet": "John Doe","domaine_expertise": "Informatique, développement logiciel","date_diplome_principal": "2015","annees_experience": 10,"nationalite": "Française","diplomes": ["Master informatique"]},{"fichier": "candidat.docx","nom_complet": "Jane Smith","domaine_expertise": "Électronique, systèmes embarqués","date_diplome_principal": "2017","annees_experience": 8,"nationalite": "Tunisienne","diplomes": ["Ingénieur en électronique"]} ] 
Résumé visuel pipeline
plaintextCopierModifierUpload CV (PDF/DOCX)  --> Save file in uploads/
          |
          v
 DOCX? ---Yes---> Convert DOCX to PDF in temp/
          |               |
          No              v
          |       Extract text from PDF (pdfplumber + OCR)
          v               |
  Extract text directly    v
          |       Clean & chunk text
          v               |
      For each chunk: ask_groq(prompt) -- Extract JSON --> Merge results
          |
          v
 Save full text in extraction.json
 Save structured data in results.json
          |
          v
     Return JSON result via API
