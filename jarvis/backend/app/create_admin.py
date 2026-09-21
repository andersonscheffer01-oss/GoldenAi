from __future__ import annotations

from getpass import getpass

from .audit import registrar_auditoria
from .database import SessionLocal, init_db
from .models import Usuario
from .security import hash_password


def main() -> None:
    init_db()
    nome = input("Nome do administrador: ").strip()
    email = input("Email do administrador: ").strip().lower()
    senha = getpass("Senha do administrador: ")
    confirmar = getpass("Confirmar senha: ")

    if not nome or not email or not senha:
        raise SystemExit("Nome, email e senha sao obrigatorios.")
    if senha != confirmar:
        raise SystemExit("As senhas nao conferem.")
    if len(senha) < 8:
        raise SystemExit("A senha precisa ter pelo menos 8 caracteres.")

    with SessionLocal() as db:
        exists = db.query(Usuario).filter(Usuario.email == email).first()
        if exists:
            raise SystemExit("Ja existe um usuario com este email.")
        usuario = Usuario(nome=nome, email=email, senha_hash=hash_password(senha), ativo=True)
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        registrar_auditoria(db, usuario.id, "cadastro_admin", "auth", "Administrador inicial criado", "local", True)
        print("Administrador criado com sucesso.")


if __name__ == "__main__":
    main()

