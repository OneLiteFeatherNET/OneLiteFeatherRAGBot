# LamaIndex Workflow Integration To-Do

## Ziel
Erstelle einen klaren Prompt, mit dem der Discord-Chatbot LamaIndex-Workflows anstößt, damit die Antworten automatisch Zugang zu Retrieval, Tool-Execution und Quality Checks bekommen. Alles in dieser Datei dient als Prompt, das heißt: Formuliere Schritte und Bedingungen so, dass sie von einem Tester oder dem Bot selbst direkt übernommen werden können.

## Prompt-gedanken (direkt nutzen)
1. "Nutze den LamaIndex `RetrieverQueryEngine`, um relevante Knoten aus der `data_<table>`-Tabelle zu holen, bevor du antwortest. Füge zu Beginn 2-3 relevante Knoten-IDs in eine temporäre Liste, damit wir später nachvollziehen können, welcher Kontext verwendet wurde."
2. "Wenn die Frage Unsicherheit enthält oder die besten Scores unter `APP_RAG_GATE_THRESHOLD` liegen, starte sofort einen LamaIndex-Agenten mit einem `ToolExecutor`, der die Antwort zunächst nachprüft (z. B. Formatprüfung, Stichwortverifikation) und gegebenenfalls zusätzliche Quellen abruft." 
3. "Wenn ein Tool-Call stattfindet, protokolliere ihn im Response-Metadatenfeld `workflow_tools` (z. B. `["summary_tool", "code_reviewer"]`), damit wir später Metriken zur Tool-Nutzung auswerten können.
4. "Füge im Prompt explizit hinzu: `Achte darauf, jede Antwort in der Sprache des Nutzers zu schreiben und gib am Ende kurz an, ob LamaIndex-Workflows (Retriever, ToolExecutor) verwendet wurden.`"
5. "Schreibe eine Feedback-Schleife in den Prompt: nach jeder Antwort soll der Bot eine Liste von Verbesserungs-Checkpunkten ausgeben, z. B. `Sources`, `Confidence`, `Next Steps`. Diese Liste soll dem QA-Team erlauben, den LamaIndex-Workflow zu bewerten.

## To-Do
- [ ] Eingangsfrage anpassen, damit die Prompt-Routine automatisch `RetrieverQueryEngine` + `ToolExecutor` startet, wenn Scores unsicher sind.
- [ ] Den `ToolExecutor` konfigurieren, um definierte Quality-Tools aufzurufen (z. B. `format_checker`, `plagiat_scanner`), und das Ergebnis in `workflow_tools` zu dokumentieren.
- [ ] Prometheus/Logs mit den neuen `workflow_tools`-Events und Score-Verteilungen erweitern, damit die Qualitätserhebung automatisiert ist.
- [ ] Sicherstellen, dass die Prompt-Indikation für Sprache, Tools und Quellen auch per Mention/Reply funktioniert (nicht nur Slash-Command).

## Nächste Schritte
Führe die in der Checkliste markierten Tasks morgen früh der Reihe nach aus; sobald sie erledigt sind, können wir in den Tests die Antwortqualität im Channel messen.
