"""Louis OS chat v8: autonomous ownership of explicitly approved GitHub actions."""
from __future__ import annotations

from atlas import louis_chat_v7 as v7
from atlas import louis_chat_v6 as chat
from atlas.autonomous_action_bridge import is_explicit_github_approval, queue_approved_action

_original_reply = chat._reply


def _autonomous_reply(session_id: str, user_text: str) -> str:
    if is_explicit_github_approval(user_text):
        chat._save(session_id, "user", user_text)
        state = chat.snapshot()
        action = queue_approved_action(
            chat._firestore(), session_id=session_id, message=user_text, state=state
        )
        target = action.get("target_url") or "le candidat GitHub actuellement classé premier"
        answer = (
            "Autorisation enregistrée. Cette mission est désormais ma responsabilité, pas la tienne.\n\n"
            f"Action autonome créée : {action['action_id']}\n"
            f"Cible : {target}\n"
            "Statut : approved_ready\n\n"
            "Je vais moi-même inspecter les exigences, préparer l'implémentation, créer les artefacts de travail, "
            "faire avancer les tests et préparer la soumission GitHub. Je ne te redemanderai d'intervenir que pour "
            "une étape réellement humaine telle qu'un KYC, une signature, un paiement ou une authentification forte."
        )
        chat._save(session_id, "assistant", answer)
        return answer

    answer = _original_reply(session_id, user_text)
    delegation_markers = (
        "rends-toi sur", "visiter l'opportunité", "tu devras", "pour toi", "engager ton expertise",
        "une fois que tu auras commencé", "tu pourras alors y contribuer",
    )
    if any(marker in answer.casefold() for marker in delegation_markers):
        answer += (
            "\n\nCorrection de responsabilité : lorsqu'une action a été explicitement autorisée et qu'elle est "
            "réalisable par logiciel, elle relève de moi, Louis OS. Je dois l'exécuter ou créer une action "
            "d'exécution traçable, pas la déléguer à l'utilisateur."
        )
        chat._save(session_id, "assistant", answer)
    return answer


chat._reply = _autonomous_reply
chat.Handler.server_version = "LouisChat/8.0"


def main() -> None:
    print("Louis Chat 8.0 listening with autonomous action ownership", flush=True)
    chat.ThreadingHTTPServer(("0.0.0.0", chat.PORT), chat.Handler).serve_forever()


if __name__ == "__main__":
    main()
