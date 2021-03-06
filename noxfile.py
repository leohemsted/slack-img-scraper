import nox_poetry as nox


@nox.session(python="3.9")
def tests(session):
    session.install("pytest")
    session.run("pytest")


@nox.session
def lint(session):
    session.install("flake8", "flake8-black", "flake8-bugbear", "flake8-import-order")
    session.install("black")
    session.install("isort")
    session.run("black", "--check", ".")
    session.run("isort", "--check", ".")
    session.run("flake8", ".")
