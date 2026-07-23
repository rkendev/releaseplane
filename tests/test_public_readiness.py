"""Public-readiness guards: .gitignore secret coverage, the brand guard, and the
demo overlay's exposure boundary.

Repo-level checks that back the public flip. They live in the root tests/ tree
(run by `make lattice` and the CI "Repo-level guards" step), not the package
testpaths, because they assert properties of the repository itself rather than of
any one package.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BRAND_GUARD = REPO_ROOT / "tools" / "brand_guard.py"
BASE_COMPOSE = REPO_ROOT / "infra" / "docker-compose.yml"
DEMO_COMPOSE = REPO_ROOT / "infra" / "docker-compose.demo.yml"
ADMIN_COMPOSE = REPO_ROOT / "infra" / "docker-compose.admin.yml"
CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
CADDY_VHOSTS = REPO_ROOT / "infra" / "caddy" / "releaseplane.Caddyfile"


def _is_ignored(relpath: str) -> bool:
    """Whether git ignores a path, via check-ignore (exit 0 means ignored)."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", relpath],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


def _is_tracked(relpath: str) -> bool:
    """Whether git tracks a path, via ls-files (nonempty output means tracked)."""
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", relpath],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def test_gitignore_covers_secrets_dir() -> None:
    # A stray secret file under infra/secrets/ must be ignored, and the .gitkeep
    # placeholder must stay tracked so the directory survives a fresh clone.
    assert _is_ignored("infra/secrets/postgres_password")
    assert _is_ignored("infra/secrets/anything.pem")
    assert not _is_ignored("infra/secrets/.gitkeep")
    assert _is_tracked("infra/secrets/.gitkeep")


def test_gitignore_covers_env_and_graphify() -> None:
    assert _is_ignored(".env")
    assert _is_ignored("graphify-out/nodes.json")
    # The committed example env file must stay tracked despite the .env.* ignore
    # (the !.env.example negation holds), so a fresh clone can copy it.
    assert not _is_ignored("infra/.env.example")
    assert _is_tracked("infra/.env.example")


def _run_brand_guard(*paths: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRAND_GUARD), *paths],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_brand_guard_flags_a_planted_token(tmp_path: Path) -> None:
    # Build the token at runtime so this test file does not itself carry it.
    brand = "co" + "work"
    planted = tmp_path / "note.md"
    planted.write_text(f"see the {brand} mirror\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "brand guard" in result.stderr


def test_brand_guard_flags_the_kb_path(tmp_path: Path) -> None:
    fragment = "Architecting_" + "Domain_Driven"
    planted = tmp_path / "note.md"
    planted.write_text(f"path: {fragment}\\KB\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "KB directory path" in result.stderr


def test_brand_guard_flags_a_token_in_the_path(tmp_path: Path) -> None:
    # A brand token in the filename is caught even when the content is clean.
    brand = "co" + "work"
    planted = tmp_path / f"{brand}_notes.md"
    planted.write_text("clean content\n", encoding="utf-8")
    result = _run_brand_guard(str(planted))
    assert result.returncode == 1
    assert "in path" in result.stderr


def _init_repo_with(tmp_path: Path, filename: str, content: str) -> Path:
    """A throwaway git repo with one commit, so --history is tested independently
    of this repo's actual history (which stays dirty until the pre-flip scrub)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *args: subprocess.run(  # noqa: E731
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    run("init", "-q")
    (repo / filename).write_text(content, encoding="utf-8")
    run("add", "-A")
    run("commit", "-qm", "seed")
    return repo


def _history_scan(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(BRAND_GUARD), "--history"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )


def test_brand_guard_history_flags_a_token_in_an_old_commit(tmp_path: Path) -> None:
    brand = "co" + "work"
    repo = _init_repo_with(tmp_path, "old.md", f"see the {brand} mirror\n")
    result = _history_scan(repo)
    assert result.returncode == 1
    assert "scrub history" in result.stderr


def test_brand_guard_history_clean_repo_passes(tmp_path: Path) -> None:
    repo = _init_repo_with(tmp_path, "clean.md", "ReleasePlane control plane.\n")
    assert _history_scan(repo).returncode == 0


def test_brand_guard_passes_clean_file(tmp_path: Path) -> None:
    clean = tmp_path / "clean.md"
    clean.write_text("ReleasePlane is a control plane for LLM releases.\n", encoding="utf-8")
    assert _run_brand_guard(str(clean)).returncode == 0


def test_brand_guard_excludes_itself() -> None:
    # The guard source necessarily contains the denied tokens; scanning it must
    # not fail, or the guard could never live in the tree it protects.
    assert _run_brand_guard(str(BRAND_GUARD)).returncode == 0


class _TaggedList(list[Any]):
    """A YAML sequence that carried a compose merge tag, keeping the tag name so a
    test can assert on it structurally rather than by grepping the file."""

    tag: str = ""


class _TaggedStr(str):
    """The same, for a tagged scalar. `ports: !reset null` is a scalar node, and
    the tag is the part that matters."""

    tag: str = ""


class _ComposeLoader(yaml.SafeLoader):
    """Compose's merge tags (`!override`, `!reset`) are not standard YAML, so a
    plain safe_load raises on them."""


def _keep_tag(loader: yaml.SafeLoader, suffix: str, node: yaml.Node) -> Any:
    if isinstance(node, yaml.SequenceNode):
        seq = _TaggedList(loader.construct_sequence(node, deep=True))
        seq.tag = suffix
        return seq
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    scalar = _TaggedStr(loader.construct_scalar(node))
    scalar.tag = suffix
    return scalar


_ComposeLoader.add_multi_constructor("!", _keep_tag)


def _services(path: Path) -> dict[str, dict[str, Any]]:
    # S506 flags yaml.load with a non-safe loader. _ComposeLoader subclasses
    # SafeLoader and adds one constructor that builds plain lists, dicts, and
    # strings, so it constructs no arbitrary objects; the subclass exists only to
    # tolerate compose's merge tags. `!!python/...` still resolves through the
    # SafeLoader table and is still rejected.
    parsed = yaml.load(path.read_text(encoding="utf-8"), Loader=_ComposeLoader)  # noqa: S506
    return dict(parsed.get("services", {}))


def _bind_address(entry: Any) -> str | None:
    """The host interface a port entry binds, or None for every interface.

    Short form is a string, `"127.0.0.1:9090:9090"`, where a two-part value like
    `"9090:9090"` names no interface. Long form is a mapping whose `host_ip` is
    optional. Both absences mean the same thing and are reported as None rather
    than as the wildcard address, so the assertion below tests for loopback rather
    than against a list of ways to be wrong.
    """
    if isinstance(entry, dict):
        host_ip = entry.get("host_ip")
        return str(host_ip) if host_ip else None
    parts = str(entry).split(":")
    return parts[0] if len(parts) >= 3 else None


def _published_ports(path: Path) -> dict[str, tuple[list[Any], str]]:
    """Services declaring `ports:`, mapped to the port entries and the merge tag
    on that node (empty string when untagged).

    Keyed on the presence of `ports:`, not on it being non-empty, so a service
    that publishes nothing at all reads as covered. `!override []` and `!reset`
    both mean that, and both are stricter than a loopback bind; a guard should not
    push a maintainer away from the safer option. A non-sequence node (`!reset
    null`) is normalized to an empty list for the same reason.
    """
    out: dict[str, tuple[list[Any], str]] = {}
    for name, body in _services(path).items():
        if "ports" not in body:
            continue
        ports = body["ports"]
        # A non-sequence node cannot publish anything, so it normalizes to no
        # entries. Iterating a bare string here would test it character by
        # character and fail on the safest setting there is.
        entries = list(ports) if isinstance(ports, list) else []
        out[name] = (entries, getattr(ports, "tag", ""))
    return out


# The load-bearing security property of the demo overlay: a service the base
# publishes must not keep its 0.0.0.0 binding once the overlay is composed in.
# Parsing the files catches a service added to the base later and never added
# here, which a one-time manual check cannot.


def test_demo_overlay_covers_every_published_service() -> None:
    missing = set(_published_ports(BASE_COMPOSE)) - set(_published_ports(DEMO_COMPOSE))
    assert not missing, (
        f"services published by the base compose with no loopback rebind in "
        f"{DEMO_COMPOSE.name}: {sorted(missing)}"
    )


@pytest.mark.parametrize("service,entry", sorted(_published_ports(DEMO_COMPOSE).items()))
def test_demo_overlay_binds_loopback_only(service: str, entry: tuple[list[Any], str]) -> None:
    ports, _tag = entry
    for port in ports:
        bind = _bind_address(port)
        assert bind == "127.0.0.1", (
            f"{service} publishes {port!r} in {DEMO_COMPOSE.name}, binding "
            f"{bind or 'every interface'}; the demo overlay must bind every "
            f"service to loopback"
        )


@pytest.mark.parametrize("service,entry", sorted(_published_ports(DEMO_COMPOSE).items()))
def test_demo_overlay_replaces_rather_than_appends_ports(
    service: str, entry: tuple[list[Any], str]
) -> None:
    # Without a merge tag compose appends to the base list and the base's 0.0.0.0
    # entry survives alongside the loopback one, so the tag is the difference
    # between a closed port and an open one. Asserted per service off the parsed
    # node, so a stray mention of the tag in a comment cannot stand in for a real
    # one. `!reset` is accepted alongside `!override`: it publishes nothing, which
    # is stricter still.
    _ports, tag = entry
    assert tag in {"override", "reset"}, (
        f"{service} in {DEMO_COMPOSE.name} declares ports without `!override` or "
        f"`!reset`; compose would append to the base list and keep its 0.0.0.0 binding"
    )


def test_base_compose_does_not_enable_anonymous_grafana() -> None:
    # Secure-by-default: anonymous access exists only in the opt-in overlay, so a
    # plain bring-up never serves Grafana without a login. This reads the inline
    # `environment:` mapping, which is where both files set Grafana's config; an
    # env_file or a mounted grafana.ini would need its own check.
    base_env = _services(BASE_COMPOSE)["grafana"].get("environment", {})
    assert not any("ANONYMOUS" in key for key in base_env)
    demo_env = _services(DEMO_COMPOSE)["grafana"]["environment"]
    assert demo_env["GF_AUTH_ANONYMOUS_ENABLED"] == "true"
    assert demo_env["GF_AUTH_ANONYMOUS_ORG_ROLE"] == "Viewer"
    assert demo_env["GF_USERS_ALLOW_SIGN_UP"] == "false"


def test_demo_overlay_leaves_no_authenticated_path_public() -> None:
    # The proxy forwards the whole Grafana surface, so a login form on it is a
    # public credential oracle and nothing rate-limits by source. Both
    # authentication paths stay off for as long as the overlay is what faces the
    # internet, and outbound snapshot sharing stays off with them.
    demo_env = _services(DEMO_COMPOSE)["grafana"]["environment"]
    assert demo_env["GF_AUTH_DISABLE_LOGIN_FORM"] == "true"
    assert demo_env["GF_AUTH_BASIC_ENABLED"] == "false"
    assert demo_env["GF_SNAPSHOTS_EXTERNAL_ENABLED"] == "false"


def _caddy_upstreams() -> list[str]:
    """Every upstream address in the tracked vhost fragment.

    Three forms have to be read, because each hides the address somewhere else:
    the one-liner, the block form (`reverse_proxy 127.0.0.1:3000 {`), and a `to`
    subdirective inside a block, which names no address on the directive line at
    all. All tokens after the directive are taken, not the first, so a
    load-balanced list yields every backend rather than only the acceptable one.
    """
    upstreams = []
    for line in CADDY_VHOSTS.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for directive in ("reverse_proxy", "forward_auth", "to"):
            if stripped.startswith(f"{directive} "):
                for token in stripped.split()[1:]:
                    if token.startswith("{"):
                        break
                    upstreams.append(token)
    return upstreams


# What the public vhost forwards, read from the vhost file rather than restated.
# The admin overlay has to vacate this port, and deriving it here means the two
# guards cannot drift apart.
PROXIED_GRAFANA_PORT = "3000"


def test_proxied_grafana_port_matches_the_vhost() -> None:
    assert f"127.0.0.1:{PROXIED_GRAFANA_PORT}" in _caddy_upstreams(), (
        f"the vhost no longer forwards {PROXIED_GRAFANA_PORT}; the admin-overlay "
        f"guard below is checking a port nothing proxies"
    )


def test_admin_overlay_keeps_the_loopback_binds() -> None:
    # The admin overlay layers on top of the demo one to reopen the login. It must
    # never widen a binding: a bring-up that drops the demo overlay to administer
    # Grafana would put every service back on 0.0.0.0, which is a far larger hole
    # than the login it reopens.
    for service, (ports, _tag) in _published_ports(ADMIN_COMPOSE).items():
        for port in ports:
            assert _bind_address(port) == "127.0.0.1", (
                f"{service} publishes {port!r} in {ADMIN_COMPOSE.name} without a " f"loopback bind"
            )
    admin_env = _services(ADMIN_COMPOSE)["grafana"]["environment"]
    assert admin_env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"


def test_admin_overlay_moves_grafana_off_the_proxied_port() -> None:
    # Reopening the login is only safe if the instance leaves the port the public
    # vhost forwards. Otherwise an admin session puts the login form, backed by the
    # real admin password, on the public hostname for as long as it lasts. The
    # vhost's upstream must be dead during the session, not merely unwelcoming.
    ports, _tag = _published_ports(ADMIN_COMPOSE)["grafana"]
    assert ports, f"{ADMIN_COMPOSE.name} must republish grafana off the proxied port"
    for port in ports:
        host_port = str(port).split(":")[1] if not isinstance(port, dict) else ""
        assert host_port != PROXIED_GRAFANA_PORT, (
            f"{ADMIN_COMPOSE.name} leaves grafana on host port "
            f"{PROXIED_GRAFANA_PORT}, which the public vhost forwards; an admin "
            f"session would serve a login form on the public hostname"
        )


# An anonymous visitor reaches Prometheus through Grafana's datasource proxy, so
# no flag that opens a write path may be set. An allowlist rather than a deny list:
# a flag added later is caught by default instead of needing its own assertion.
PROMETHEUS_ALLOWED_FLAGS = {
    "--config.file",
    "--storage.tsdb.path",
    "--storage.tsdb.retention.time",
    "--storage.tsdb.retention.size",
    "--query.timeout",
    "--query.max-samples",
}


@pytest.mark.parametrize("compose", [BASE_COMPOSE, DEMO_COMPOSE, ADMIN_COMPOSE])
def test_prometheus_exposes_no_mutating_endpoint(compose: Path) -> None:
    # Checked in every file, since `command:` replaces the list wholesale and an
    # overlay could reintroduce a flag the base does not set. No `command:` at all
    # is fine: the image default is the config path and the storage path.
    command = _services(compose).get("prometheus", {}).get("command", [])
    for flag in command:
        name = str(flag).split("=", 1)[0]
        assert name in PROMETHEUS_ALLOWED_FLAGS, (
            f"{compose.name} passes {name} to Prometheus, which is not on the "
            f"read-only allowlist; the datasource proxy is publicly reachable"
        )


def test_caddy_vhosts_reach_only_the_two_public_services() -> None:
    """The vhost file is the public attack surface expressed in one place.

    Every `reverse_proxy` upstream must be loopback (the demo overlay binds
    nothing else, so a non-loopback upstream is a mistake or a hole), and the set
    of ports it reaches must be exactly Grafana and Jaeger. A block added later
    pointing at the control plane or the gateway would put a write path on the
    internet, which is the one thing this design rules out.
    """
    upstreams = _caddy_upstreams()
    assert upstreams, f"{CADDY_VHOSTS.name} declares no reverse_proxy"
    for upstream in upstreams:
        assert upstream.startswith(
            "127.0.0.1:"
        ), f"{CADDY_VHOSTS.name} proxies {upstream!r}, which is not loopback"
    reached = {u.split(":", 1)[1] for u in upstreams}
    assert reached == {PROXIED_GRAFANA_PORT, "16686"}, (
        f"{CADDY_VHOSTS.name} reaches ports {sorted(reached)}; the public surface "
        f"is Grafana ({PROXIED_GRAFANA_PORT}) and Jaeger (16686) and nothing else"
    )


def test_caddy_vhosts_pull_in_no_other_config() -> None:
    # An `import` would bring in upstreams this file does not name, so the guard
    # above could pass while the deployed vhost reached anything at all.
    for line in CADDY_VHOSTS.read_text(encoding="utf-8").splitlines():
        assert not line.strip().startswith("import "), (
            f"{CADDY_VHOSTS.name} imports other config; the upstreams it reaches "
            f"must be readable from this file alone"
        )


def _caddy_site_lines() -> list[str]:
    """Every top-level line opening a site block, verbatim.

    Unindented and ending in a brace or a comma is what makes a line part of a
    site address in this file; everything else is a directive, a comment, or a
    closing brace. The comma case matters: a multi-line address list puts the
    first names on their own lines, and checking only the line that opens the
    block would leave them unexamined. Returned unparsed so the caller checks all
    of them, including scheme-prefixed forms a stricter pattern would skip.
    """
    return [
        line.strip()
        for line in CADDY_VHOSTS.read_text(encoding="utf-8").splitlines()
        if not line.startswith((" ", "\t", "#")) and line.strip().endswith(("{", ","))
    ]


def test_caddy_vhosts_carry_no_real_hostname() -> None:
    # The file is tracked and the repo goes public, so the host it runs on stays a
    # placeholder here and lives in the gitignored infra/.env, same as the ports.
    # Every site line is checked rather than only the ones a pattern recognizes, so
    # a substitution is caught whatever it substitutes in, including a bare IP or a
    # second name added after a comma.
    sites = _caddy_site_lines()
    assert sites, f"{CADDY_VHOSTS.name} declares no site address"
    for site in sites:
        for address in site.removesuffix("{").replace(",", " ").split():
            assert "<demo-host>" in address, (
                f"{CADDY_VHOSTS.name} serves {address!r}, which names a real host; "
                f"the tracked copy keeps the <demo-host> placeholder"
            )


# Paths the vhost must refuse. Grafana counts an anonymous visitor as signed in, so
# each of these answered before it was closed; docs/SECURITY.md records what each
# one returned. The trailing-slash form is listed because Caddy's path matcher is
# exact and Grafana's router accepted both.
REFUSED_PATHS = (
    "/api/short-urls",
    "/api/short-urls/*",
    "/api/gnet/*",
    "/api/frontend-metrics",
    "/api/live/publish",
)


def test_caddy_vhosts_refuse_the_anonymous_write_paths() -> None:
    text = CADDY_VHOSTS.read_text(encoding="utf-8")
    matcher = [line for line in text.splitlines() if line.strip().startswith("@refused path ")]
    assert matcher, f"{CADDY_VHOSTS.name} has no @refused path matcher"
    declared = matcher[0].split("@refused path ", 1)[1].split()
    for path in REFUSED_PATHS:
        assert path in declared, (
            f"{CADDY_VHOSTS.name} no longer refuses {path}; it is reachable "
            f"anonymously and docs/SECURITY.md says it is closed"
        )
    assert "respond @refused" in text

    # These paths are Grafana's, so the refusal has to sit in the Grafana site
    # block. Matching on the file as a whole would stay green if the matcher and
    # its respond moved into the Jaeger block, leaving Grafana wide open.
    grafana_block = text.split(f"reverse_proxy 127.0.0.1:{PROXIED_GRAFANA_PORT}", 1)[0]
    assert "@refused path " in grafana_block
    assert "respond @refused" in grafana_block


def test_caddy_vhosts_log_every_site() -> None:
    # docs/SECURITY.md accepts a compute-exhaustion risk on the grounds that it is
    # observable. That holds only while both sites log; Caddy logs per site and
    # this host sets no global default.
    text = CADDY_VHOSTS.read_text(encoding="utf-8")
    assert text.count("log {") == len(_caddy_site_lines())


def test_demo_make_targets_include_the_overlay() -> None:
    # The runbook points at these targets as the thing that keeps a bring-up from
    # forgetting the overlay, so the file list they carry is load-bearing. The
    # parsing guards above check what the overlay says; this checks that the
    # documented way to run it actually composes it in.
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "-f infra/docker-compose.demo.yml" in makefile
    for target in ("demo-up:", "demo-admin:", "demo-config:"):
        assert target in makefile, f"Makefile has no {target} target"
    # demo-admin layers, never replaces: it names the admin file in addition to
    # the shared DEMO_COMPOSE invocation rather than building its own list.
    admin_recipe = makefile.split("demo-admin:", 1)[1].split("\n\n", 1)[0]
    assert "$(DEMO_COMPOSE)" in admin_recipe
    assert "-f infra/docker-compose.admin.yml" in admin_recipe


def test_ci_postgres_matches_the_dev_stack_digest() -> None:
    # CI claims parity with the dev stack by pinning the same Postgres digest, and
    # nothing enforced that. Now that Dependabot moves the compose pins, the two
    # would drift on the first bump: the docker-compose updater does not touch a
    # workflow's `services.image`, so the bump has to carry this by hand.
    compose_image = _services(BASE_COMPOSE)["postgres"]["image"]
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    assert compose_image in workflow, (
        f"the CI postgres service does not pin {compose_image}; the workflow says "
        f"it matches the dev stack, so a compose bump has to move both"
    )


def test_working_tree_is_brand_clean() -> None:
    # The live gate: every tracked file passes the guard right now.
    tracked = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    result = _run_brand_guard(*tracked)
    assert result.returncode == 0, result.stderr
