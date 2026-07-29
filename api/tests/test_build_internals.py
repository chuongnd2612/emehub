"""The pieces a hub-side build is assembled from (ADR 0007).

``test_knowledge_build.py`` covers the behaviour the endpoint promises. This
file covers the parts underneath it, each of which has one property that would
be expensive to discover in production:

* **workspace_scope** — a user-supplied project key cannot escape its scope
  directory, and two members never share one.
* **claude_credentials.materialize** — the plaintext lands under the workspace
  and nowhere else, and is locked down.
* **repo_service** — the authenticated URL is built correctly and redacted
  unconditionally.
* **claude_cli** — the CLI is invoked without a tool allowlist, the credential
  is passed by environment rather than argument, and usage is attributed.
* **write_knowledge_files** — a test-account password is never written to disk.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys

import pytest

from app import crypto
from app.config import settings
from app.models.claude_credentials import ClaudeCredentials
from app.models.knowledge import ProjectKnowledge, compose_key
from app.models.project_config import ProjectConfig
from app.services import claude_cli, claude_credentials, knowledge_service, repo_service
from app.services import workspace_scope as ws

PASSWORD = "password12345"
PAT = "ghp_atokenthatmustnotescape0123456789"

CREDENTIAL = json.dumps(
    {
        "claudeAiOauth": {
            "accessToken": "sk-ant-oat-do-not-log-me",
            "refreshToken": "sk-ant-ort-also-secret",
            "expiresAt": 4_102_444_800_000,
            "scopes": ["user:inference"],
            "subscriptionType": "Max",
        }
    }
)


# ------------------------------------------------------------ workspace scope
def test_a_scope_is_per_owner_and_shared_is_its_own(workspace_dir):
    assert ws.scope_for(7) == "users/7"
    assert ws.scope_for(None) == "shared"
    assert ws.scoped_repos_dir(7) != ws.scoped_repos_dir(8)
    assert ws.scoped_repos_dir(7) != ws.scoped_repos_dir(None)


def test_every_scoped_dir_stays_inside_the_workspace(workspace_dir):
    root = settings.workspace_path.resolve()
    for kind in ws.KINDS:
        for owner in (None, 1):
            assert ws.scoped_dir(kind, owner).resolve().is_relative_to(root)


def test_an_unknown_kind_is_refused(workspace_dir):
    """A typo must not quietly create a stray tree in the credential volume."""
    with pytest.raises(ValueError, match="Unknown workspace kind"):
        ws.scoped_dir("evidence", 1)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../etc", "etc"),
        ("/etc/passwd", "etc-passwd"),
        ("..", "project"),
        ("", "project"),
        ("Surency Platform", "Surency-Platform"),
        ("a/b/c", "a-b-c"),
    ],
)
def test_a_project_key_cannot_escape_its_scope(raw, expected):
    assert ws.slug(raw) == expected


def test_a_traversing_key_resolves_inside_the_scope(workspace_dir):
    scope = ws.scoped_repos_dir(3).resolve()
    assert (scope / ws.slug("../../../root")).resolve().is_relative_to(scope)


# ------------------------------------------------------------ materialisation
def test_materialize_writes_the_plaintext_only_under_the_workspace(db_session):
    row = ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL))
    db_session.add(row)
    db_session.commit()

    config_dir = claude_credentials.materialize(row)

    assert config_dir.resolve().is_relative_to(settings.workspace_path.resolve())
    assert config_dir == ws.scoped_claude_config_dir(None)
    assert (config_dir / ".credentials.json").read_text(encoding="utf-8") == CREDENTIAL


def test_materialize_keys_off_the_credentials_owner_not_the_requester(db_session, make_user):
    """A member running under the shared account shares its materialised copy
    rather than minting a second plaintext of the same secret."""
    alice = make_user("alice@emesoft.net", PASSWORD)
    shared = ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL))
    db_session.add(shared)
    db_session.commit()

    resolved = claude_credentials.resolve_effective_config_dir(db_session, alice.id)

    assert resolved is not None
    config_dir, source = resolved
    assert source == "shared"
    assert config_dir == ws.scoped_claude_config_dir(None)


@pytest.mark.skipif(sys.platform == "win32", reason="chmod is a no-op on Windows")
def test_the_materialised_credential_is_locked_down(db_session):
    row = ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL))
    db_session.add(row)
    db_session.commit()

    config_dir = claude_credentials.materialize(row)

    assert stat.S_IMODE(config_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((config_dir / ".credentials.json").stat().st_mode) == 0o600


def test_an_undecryptable_credential_is_not_written_as_ciphertext(db_session):
    row = ClaudeCredentials(owner_id=None, credentials="enc::v1:not-a-real-token")
    db_session.add(row)
    db_session.commit()

    with pytest.raises(claude_credentials.ClaudeCredentialsError):
        claude_credentials.materialize(row)
    assert not (ws.scoped_claude_config_dir(None) / ".credentials.json").exists()


def test_no_credential_resolves_to_none_rather_than_an_empty_file(db_session):
    assert claude_credentials.resolve_effective_config_dir(db_session, None) is None


# -------------------------------------------------------------- redaction
@pytest.mark.parametrize(
    "text",
    [
        f"fatal: Authentication failed for 'https://{PAT}@github.com/a/b.git'",
        f"remote: token {PAT} is invalid",
        f"could not read from https://x-access-token:{PAT}@github.com/a/b",
    ],
)
def test_redact_removes_the_pat_however_git_phrased_it(text):
    cleaned = repo_service.redact(text, PAT)
    assert PAT not in cleaned


def test_redact_strips_userinfo_even_for_a_credential_we_never_saw():
    """The structural rule has to work without knowing the secret — git can echo
    a credential it found in its own config, not one we injected."""
    cleaned = repo_service.redact("https://someoneelse:hunter2@example.com/x")
    assert "hunter2" not in cleaned
    assert "***@example.com" in cleaned


def test_the_pat_is_injected_only_into_a_credential_free_https_url():
    inject = repo_service._authenticated_url
    assert (
        inject("https://github.com/a/b.git", PAT)
        == f"https://x-access-token:{PAT}@github.com/a/b.git"
    )
    # Already carries credentials — never rewritten.
    assert inject("https://u:p@github.com/a/b.git", PAT) == "https://u:p@github.com/a/b.git"
    # Not HTTPS — nothing to inject into.
    assert inject("git@github.com:a/b.git", PAT) == "git@github.com:a/b.git"
    # No PAT — a public clone stays anonymous.
    assert inject("https://github.com/a/b.git", "") == "https://github.com/a/b.git"


def test_the_pat_lands_in_the_password_position_not_the_username():
    """Issue #62. A PAT as the bare username is a username whose password is
    still missing, so git asks for one — ``could not read Password for
    'https://***@dev.azure.com'`` on every private clone, because the container
    has no TTY to ask on."""
    url = repo_service._authenticated_url("https://dev.azure.com/org/proj/_git/r", PAT)

    userinfo = url.split("//", 1)[1].split("@", 1)[0]
    assert ":" in userinfo, url
    username, _, password = userinfo.partition(":")
    assert password == PAT
    assert username and username != PAT
    # And the host survived intact — the PAT did not re-parse the authority.
    assert url.endswith("@dev.azure.com/org/proj/_git/r")


def test_an_ado_url_with_a_bare_org_username_still_gets_the_pat():
    """Issue #62, second failure — the one the first fix missed.

    Azure DevOps hands out clone URLs shaped
    ``https://<org>@dev.azure.com/<org>/<project>/_git/<repo>``: the org name
    sits in the userinfo with **no password**. The first fix bailed on any
    ``@`` ("never rewrite someone else's credential"), so every real ADO URL
    still reached git as a username with no password and died with
    ``could not read Password``. A bare username is not a credential — the
    password is exactly what is missing.
    """
    from urllib.parse import urlparse

    url = repo_service._authenticated_url(
        "https://DDKS@dev.azure.com/DDKS/Surency/_git/surency-admin-hub", PAT
    )

    parsed = urlparse(url)
    assert parsed.username == "DDKS", "the org username should be kept"
    assert parsed.password == PAT, "the PAT belongs in the password half"
    assert parsed.hostname == "dev.azure.com"
    assert parsed.path == "/DDKS/Surency/_git/surency-admin-hub"
    assert PAT not in repo_service.redact(url, PAT)


def test_a_real_embedded_credential_is_still_never_overwritten():
    """The guard that motivated the original bail-out is kept, narrowed to what
    it was actually for: userinfo carrying a *password* is a credential someone
    embedded deliberately, and quietly authenticating as somebody else would be
    worse than failing."""
    original = "https://someone:theirsecret@dev.azure.com/org/proj/_git/r"
    assert repo_service._authenticated_url(original, PAT) == original


def test_a_url_unsafe_pat_is_percent_encoded_rather_than_re_parsing_the_url():
    """An ADO PAT is opaque provider output and may hold ``/`` or ``@``; a raw
    one in the userinfo would silently move the host into the path."""
    from urllib.parse import unquote, urlparse

    awkward = "pat/with+odd:chars@and#hash"
    url = repo_service._authenticated_url("https://dev.azure.com/org/_git/r", awkward)

    parsed = urlparse(url)
    assert parsed.hostname == "dev.azure.com"
    assert parsed.path == "/org/_git/r"
    # git percent-decodes the userinfo before sending it, so the PAT arrives whole.
    assert unquote(parsed.password or "") == awkward
    assert awkward not in url  # ...but the literal never appears on the wire


@pytest.fixture
def alice_with_pat(db_session, make_user):
    """A user holding a GitHub connection whose PAT is :data:`PAT`."""
    from app.models.provider_connection import ProviderConnection
    from app.services import connection_service

    alice = make_user("alice@emesoft.net", PASSWORD)
    db_session.add(
        ProviderConnection(
            kind="github",
            label="GitHub",
            pat_encrypted=crypto.encrypt(PAT),
            capabilities=connection_service.default_capabilities("github"),
            owner_id=alice.id,
        )
    )
    db_session.commit()
    return alice


def test_git_runs_with_prompting_switched_off(db_session, alice_with_pat, monkeypatch):
    """Issue #62, the other half: with no askpass neutralisation a bad PAT is
    either a prompt (instant, illegible) or a hang until ``clone_timeout_s``."""
    # A hostile ambient environment — exactly what must not survive into git.
    monkeypatch.setenv("GIT_ASKPASS", "/usr/bin/some-gui-prompt")
    monkeypatch.setenv("SSH_ASKPASS", "/usr/bin/some-gui-prompt")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")
    monkeypatch.setenv("GCM_INTERACTIVE", "always")

    seen: dict = {}

    def capture(argv, **kwargs):
        seen["argv"] = argv
        seen["env"] = kwargs.get("env")
        return _Completed("", returncode=128, stderr="fatal: repository not found")

    monkeypatch.setattr(subprocess, "run", capture)

    with pytest.raises(repo_service.CloneError):
        repo_service.ensure_clone(
            db_session,
            project_key="p",
            repo_name="web",
            repo_url="https://github.com/a/b.git",
            owner_id=alice_with_pat.id,
            bound_connection_id=None,
        )

    env = seen["env"]
    assert env is not None, "git must be given an explicit environment"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert not env["GIT_ASKPASS"]
    assert not env["SSH_ASKPASS"]
    assert env["GCM_INTERACTIVE"] == "never"
    # Inherited, because git cannot resolve a host or a certificate without it.
    assert env.get("PATH") == os.environ.get("PATH")


def test_the_pat_reaches_git_but_never_the_error_or_the_log(
    db_session, alice_with_pat, monkeypatch, caplog
):
    """Non-vacuous by construction: assert the PAT *was* in the argv first."""
    seen: dict = {}

    def capture(argv, **kwargs):
        seen["argv"] = argv
        # git reflecting the whole authenticated URL back at us — a real message.
        return _Completed(
            "",
            returncode=128,
            stderr=(
                f"fatal: Authentication failed for "
                f"'https://x-access-token:{PAT}@github.com/a/b.git'"
            ),
        )

    monkeypatch.setattr(subprocess, "run", capture)

    with caplog.at_level("INFO"):
        with pytest.raises(repo_service.CloneError) as raised:
            repo_service.ensure_clone(
                db_session,
                project_key="p",
                repo_name="web",
                repo_url="https://github.com/a/b.git",
                owner_id=alice_with_pat.id,
                bound_connection_id=None,
            )

    # The PAT really did go to git — otherwise everything below is vacuous.
    assert any(PAT in arg for arg in seen["argv"]), seen["argv"]

    message = str(raised.value)
    assert PAT not in message
    assert "Authentication failed" in message  # the useful part survives
    assert PAT not in caplog.text


def test_a_clone_url_is_required_and_says_what_to_do(db_session):
    with pytest.raises(repo_service.CloneError, match="Repositories"):
        repo_service.ensure_clone(
            db_session,
            project_key="p",
            repo_name="web",
            repo_url="   ",
            owner_id=None,
            bound_connection_id=None,
        )


def test_missing_git_is_reported_rather_than_raised(db_session, make_user, monkeypatch):
    """The image ships git; a host install might not. Either way it is a status."""
    from app.models.provider_connection import ProviderConnection
    from app.services import connection_service

    alice = make_user("alice@emesoft.net", PASSWORD)
    db_session.add(
        ProviderConnection(
            kind="github",
            label="GitHub",
            pat_encrypted=crypto.encrypt(PAT),
            capabilities=connection_service.default_capabilities("github"),
            owner_id=alice.id,
        )
    )
    db_session.commit()

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(repo_service.CloneError, match="git is not installed"):
        repo_service.ensure_clone(
            db_session,
            project_key="p",
            repo_name="web",
            repo_url="https://github.com/a/b.git",
            owner_id=alice.id,
            bound_connection_id=None,
        )


# ----------------------------------------------------------------- claude_cli
class _Completed:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


ENVELOPE = json.dumps(
    {
        "type": "result",
        "result": '{"branch":"main","stack":["React"],"confidence":91}',
        "usage": {"input_tokens": 1200, "output_tokens": 340},
        "total_cost_usd": 0.0412,
        "duration_ms": 8123,
    }
)


@pytest.fixture
def credential(db_session):
    row = ClaudeCredentials(owner_id=None, credentials=crypto.encrypt(CREDENTIAL))
    db_session.add(row)
    db_session.commit()
    return row


def test_run_json_passes_the_credential_by_env_never_by_argument(
    db_session, credential, monkeypatch
):
    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return _Completed(ENVELOPE)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = claude_cli.run_json("do it", db=db_session, owner_id=None, label="t")

    assert result == {"branch": "main", "stack": ["React"], "confidence": 91}
    joined = " ".join(captured["cmd"])
    assert "sk-ant-oat-do-not-log-me" not in joined
    assert captured["env"]["CLAUDE_CONFIG_DIR"] == str(ws.scoped_claude_config_dir(None))


def test_the_cli_is_never_given_tools_or_permission_skips(db_session, credential, monkeypatch):
    """The hub reads a cloned repository; it does not execute it (ADR 0007)."""
    captured: dict = {}

    def fake_run(cmd, **_kwargs):
        captured["cmd"] = cmd
        return _Completed(ENVELOPE)

    monkeypatch.setattr(subprocess, "run", fake_run)
    claude_cli.run_json("do it", db=db_session, owner_id=None)

    joined = " ".join(captured["cmd"])
    for forbidden in (
        "--allowedTools",
        "--dangerously-skip-permissions",
        "--add-dir",
        "--permission-mode",
    ):
        assert forbidden not in joined


def test_usage_is_recorded_against_the_owner_who_paid(db_session, credential, monkeypatch):
    from app.models.claude_usage import ClaudeUsage

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed(ENVELOPE))

    claude_cli.run_json("do it", db=db_session, owner_id=None, label="Build knowledge: x")

    row = db_session.query(ClaudeUsage).one()
    assert row.owner_id is None
    assert row.source == "emehub"
    assert row.credential_source == "shared"
    assert row.input_tokens == 1200
    assert row.cost_usd == pytest.approx(0.0412)
    assert row.duration_ms == 8123


def test_no_credential_is_a_clear_error_not_a_login_prompt(db_session, monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Completed(ENVELOPE))

    with pytest.raises(claude_cli.ClaudeError, match="No Claude credential"):
        claude_cli.run_json("do it", db=db_session, owner_id=None)


def test_an_auth_failure_flags_the_stored_credential(db_session, credential, monkeypatch):
    from app.models.claude_credentials import STATUS_EXPIRED

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _Completed(
            '{"is_error":true,"result":"API Error: 401 Invalid authentication credentials"}',
            returncode=1,
        ),
    )

    with pytest.raises(claude_cli.ClaudeError, match="rejected the credential"):
        claude_cli.run_json("do it", db=db_session, owner_id=None)

    db_session.refresh(credential)
    assert credential.status == STATUS_EXPIRED


def test_a_rotated_token_is_captured_back_into_the_store(db_session, credential, monkeypatch):
    """The CLI rewrites .credentials.json in place; the hub must stay authoritative."""
    rotated = json.dumps(
        {
            "claudeAiOauth": {
                "accessToken": "sk-ant-oat-rotated",
                "expiresAt": 4_202_444_800_000,
                "subscriptionType": "Max",
            }
        }
    )

    def fake_run(_cmd, **kwargs):
        config_dir = kwargs["env"]["CLAUDE_CONFIG_DIR"]
        (ws.Path(config_dir) / ".credentials.json").write_text(rotated, encoding="utf-8")
        return _Completed(ENVELOPE)

    monkeypatch.setattr(subprocess, "run", fake_run)
    claude_cli.run_json("do it", db=db_session, owner_id=None)

    db_session.refresh(credential)
    assert crypto.decrypt(credential.credentials) == rotated


def test_a_timeout_is_a_clean_error(db_session, credential, monkeypatch):
    def timeout(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(claude_cli.ClaudeError, match="timed out"):
        claude_cli.run_json("do it", db=db_session, owner_id=None, timeout=1)


def test_a_missing_cli_names_the_binary_setting(db_session, credential, monkeypatch):
    def missing(*_a, **_k):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(subprocess, "run", missing)

    with pytest.raises(claude_cli.ClaudeError, match="EMEHUB_CLAUDE_BIN"):
        claude_cli.run_json("do it", db=db_session, owner_id=None)


def test_non_json_output_fails_without_quoting_the_repository(db_session, credential, monkeypatch):
    secret_source = "const APIKEY = 'leaked-from-the-clone';"
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _Completed(json.dumps({"result": f"I found {secret_source}"})),
    )

    with pytest.raises(claude_cli.ClaudeError) as exc:
        claude_cli.run_json("do it", db=db_session, owner_id=None)
    assert secret_source not in str(exc.value)


# ---------------------------------------------------------------- the skill
def test_the_project_bootstrap_skill_ships_with_the_repo():
    from app.services.skills import PROJECT_BOOTSTRAP, load_skill

    text = load_skill(PROJECT_BOOTSTRAP, include_template=True)
    assert text and "Project Knowledge Base" in text


def test_an_unknown_skill_is_a_typo_not_a_silent_skip():
    from app.services.skills import load_skill

    with pytest.raises(ValueError, match="Unknown skill"):
        load_skill("automation-generator")


# ------------------------------------------------------------- the artefacts
def test_the_artefacts_never_carry_a_test_account_password(db_session, make_user):
    alice = make_user("alice@emesoft.net", PASSWORD)
    config = ProjectConfig(
        key="surency",
        name="Surency",
        base_url="https://app.surency.test",
        test_accounts=[
            {
                "role": "admin",
                "username": "admin@surency.test",
                "password": crypto.encrypt("s3cret-account-password"),
                "notes": "",
            }
        ],
        owner_id=alice.id,
    )
    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        confidence=88,
        knowledge={"stack": ["React"], "routes": [{"path": "/login"}]},
        owner_id=alice.id,
    )
    db_session.add_all([config, row])
    db_session.commit()

    out_dir = knowledge_service.write_knowledge_files(row, config)

    written = "\n".join(
        (out_dir / name).read_text(encoding="utf-8")
        for name in ("knowledge.json", "knowledge.md")
    )
    assert "s3cret-account-password" not in written
    assert config.test_accounts[0]["password"] not in written  # nor the ciphertext
    assert "admin@surency.test" in written  # the username is fine, and useful


def test_the_artefacts_land_in_the_owners_scope(db_session, make_user):
    alice = make_user("alice@emesoft.net", PASSWORD)
    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()

    out_dir = knowledge_service.write_knowledge_files(row, None)

    assert out_dir == ws.scoped_knowledge_dir(alice.id) / "surency" / "web"
    assert out_dir.resolve().is_relative_to(settings.workspace_path.resolve())
    assert json.loads((out_dir / "knowledge.json").read_text())["built_by"] == "emehub"


def test_the_prompt_carries_roles_but_never_a_password(db_session, make_user):
    config = ProjectConfig(
        key="surency",
        base_url="https://app.surency.test",
        test_accounts=[
            {"role": "admin", "username": "a@b.c", "password": "plain-text-oops", "notes": ""}
        ],
        environments=[{"name": "staging", "base_url": "https://staging.test"}],
    )

    hints = knowledge_service._config_hints(config)

    assert "admin" in hints
    assert "staging" in hints
    assert "plain-text-oops" not in hints


def test_the_prompt_never_advertises_an_agent_host_path(db_session):
    """`local_repo_path` names a directory on the AGENT, not in this container."""
    config = ProjectConfig(key="surency", base_url="https://app.surency.test")
    assert "local_repo_path" not in knowledge_service._config_hints(config)
    prompt = knowledge_service._build_prompt("Surency", "github", "web", "Playwright", config)
    assert "working directory" in prompt


def test_a_thin_model_response_still_produces_a_row(db_session, credential, monkeypatch):
    """A model that omits keys yields a thin knowledge base, not a KeyError."""
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: _Completed(json.dumps({"result": "{}"}))
    )

    payload = knowledge_service.build_knowledge_payload(
        db_session,
        name="Surency",
        provider="github",
        repo="web",
        framework="Playwright",
        owner_id=None,
    )

    assert payload["confidence"] == 80
    assert payload["knowledge"]["stack"] == []
    assert payload["knowledge"]["assets"] == 0


def test_confidence_is_clamped_to_the_column_range(db_session, credential, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _Completed(json.dumps({"result": '{"confidence": 4000}'})),
    )
    payload = knowledge_service.build_knowledge_payload(
        db_session, name="x", provider="", repo="", framework="", owner_id=None
    )
    assert payload["confidence"] == 100


# ------------------------------------------------------------ the happy path
def test_a_successful_build_indexes_the_row_and_writes_artefacts(
    db_session, make_user, monkeypatch, tmp_path
):
    """Everything real except the two things this environment cannot supply:
    a reachable repository and a live Claude."""
    alice = make_user("alice@emesoft.net", PASSWORD)
    db_session.add(ClaudeCredentials(owner_id=alice.id, credentials=crypto.encrypt(CREDENTIAL)))
    db_session.add(
        ProjectConfig(
            key="surency",
            name="Surency",
            base_url="https://app.surency.test",
            repos=[{"name": "web", "repo_url": "https://github.com/e/w.git", "default": True}],
            owner_id=alice.id,
        )
    )
    row = ProjectKnowledge(
        key=compose_key("surency", "web"),
        project_key="surency",
        repo="web",
        name="Surency",
        status="indexing",
        owner_id=alice.id,
    )
    db_session.add(row)
    db_session.commit()
    row_id = row.id

    clone = tmp_path / "clone"
    clone.mkdir()
    monkeypatch.setattr(repo_service, "ensure_clone", lambda *a, **k: clone)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: _Completed(
            json.dumps(
                {
                    "result": json.dumps(
                        {
                            "branch": "main",
                            "stack": ["React", "FastAPI"],
                            "routes": [{"path": "/login", "auth_required": False}],
                            "confidence": 93,
                        }
                    ),
                    "usage": {"input_tokens": 10, "output_tokens": 5},
                    "total_cost_usd": 0.01,
                }
            )
        ),
    )

    knowledge_service._run_build(row_id)

    db_session.expire_all()
    row = db_session.get(ProjectKnowledge, row_id)
    assert row.status == "indexed"
    assert row.confidence == 93
    assert row.version == "v1"
    assert row.last_error == ""
    assert row.knowledge["stack"] == ["React", "FastAPI"]

    out_dir = ws.Path(row.doc_path)
    assert out_dir.resolve().is_relative_to(settings.workspace_path.resolve())
    assert (out_dir / "knowledge.md").is_file()
    assert (out_dir / "knowledge.json").is_file()

    # A rebuild increments the version rather than resetting it.
    row.status = "indexing"
    db_session.commit()
    knowledge_service._run_build(row_id)
    db_session.expire_all()
    assert db_session.get(ProjectKnowledge, row_id).version == "v2"


def test_the_environment_is_inherited_not_replaced(db_session, credential, monkeypatch):
    """A build needs PATH (to find node/git) and the proxy vars an operator set."""
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.internal:3128")
    captured: dict = {}
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, **kw: (captured.update(kw), _Completed(ENVELOPE))[1],
    )

    claude_cli.run_json("do it", db=db_session, owner_id=None)

    assert captured["env"]["HTTPS_PROXY"] == "http://proxy.internal:3128"
    assert captured["env"].get("PATH") == os.environ.get("PATH")
