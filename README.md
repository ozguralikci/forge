# AI Software Factory

Kullanıcının doğal dille verdiği yazılım talebini araştıran, planlayan, tartışan, kodlayan, test eden, denetleyen ve teslim eden çok ajanlı yazılım şirketi işletim sistemi.

---

# FORGE v0.1 (implemented)

Everything below this heading describes code that exists and runs today. The
Turkish sections that follow describe the wider product vision, most of which is
still a plan.

## What v0.1 does

FORGE v0.1 is the deterministic execution core. It proves one thing end to end:

> A task specification goes in, a provider implements it in an isolated run
> workspace, and **an independent validation step decides PASS or FAIL from real
> command exit codes** - never from the provider's own claims. The whole run is
> reconstructable from an append-only audit log.

The flow is:

```text
task file -> TASK_READY -> IMPLEMENTING -> VALIDATING -> TASK_COMPLETED
                                ^              |
                                |              v
                                +------ FIX_REQUIRED -> BLOCKED
```

Two design decisions are worth knowing up front:

1. **Validation always runs**, even when the provider reports that it failed.
   The provider's self-report is written to the audit log as a *claim* and is
   never consulted when deciding the verdict. A provider that lies about success
   still ends in `BLOCKED`.
2. **The FakeProvider produces real evidence.** It writes an actual file into
   the run workspace, and the validation command runs as a real subprocess that
   inspects that file. When a `fail_then_succeed` run recovers on its second
   attempt, it recovers because a real process returned a different exit code.

## Install

Requires Python 3.11+ on Windows (Linux and macOS work too, but Windows is the
supported development environment).

```bash
python -m pip install -e ".[dev]"
```

## Run the tests

```bash
python -m pytest -q
```

The suite launches real subprocesses on purpose: a test that asserts a PASS
verdict is asserting that a real process exited zero.

## Run the example task

```bash
python -m forge run examples/hello_task/task.yaml
```

or, once installed, using the console script:

```bash
forge run examples/hello_task/task.yaml
```

The example uses the FakeProvider in `fail_then_succeed` mode, so it fails
validation on the first attempt, enters `FIX_REQUIRED`, and passes on the
second - ending in `TASK_COMPLETED` with verdict `PASS`.

### What a run leaves behind

```text
runs/<run_id>/
    state.json      current position, attempt counts, verdict (rewritten)
    events.jsonl    append-only audit log, one JSON object per line
    evidence/       per-command exit code, stdout, stderr, timings
    workspace/      where the provider works and validation commands run
```

Each audit event carries `event_id`, `run_id`, `timestamp`, `event_type`,
`previous_state`, `new_state`, `message` and `metadata`.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | `TASK_COMPLETED` - every validation command exited zero |
| 1 | `BLOCKED` - validation never passed within `max_fix_rounds` |
| 2 | `FAILED` - an error or the task timeout ended the run |
| 3 | `CANCELLED` - interrupted |
| 4 | the task file could not be loaded or is invalid |

## Task file format

Identity fields (`task_id`, `project_id`, `title`, `description`,
`acceptance_criteria`, `risk_level`) are validated against the repository's own
`schemas/task.schema.json`. FORGE adds three runtime sections, validated in
Python because the schema does not describe them yet:

```yaml
provider:
  name: fake                  # the only provider in v0.1
  mode: fail_then_succeed     # succeed | fail | fail_then_succeed
  artifact: result.txt        # relative to the run workspace

validation:
  commands:                   # argv lists, or strings split with shlex
    - - "${PYTHON}"           # ${PYTHON} expands to the running interpreter
      - "-c"
      - "print('hello')"

execution:
  max_fix_rounds: 3           # 1 initial attempt + up to 3 fix attempts
  command_timeout_seconds: 30
  task_timeout_seconds: 120
```

Commands run **without a shell**, so pipes, redirection and `&&` are not
available. Validation stops at the first failing command.

## Safety bounds enforced today

- `max_fix_rounds` - caps retries, then moves to `BLOCKED`
- `command_timeout_seconds` - per command, enforced by the subprocess timeout
- `task_timeout_seconds` - the budget shared by all validation commands in a
  run. It is re-read before every command, so a command is never granted more
  than `min(command_timeout_seconds, remaining task time)` and the cumulative
  validation time cannot exceed the budget. If the budget is gone before a
  command starts, that command is not launched and is recorded as timed out.
  See the limitation below for what this does **not** cover.
- Illegal state transitions raise instead of being silently ignored
- A task declaring `required_secrets` is **refused**, because v0.1 has no secret
  broker and will not pretend to honour a guarantee it cannot keep

## Deliberately not implemented yet

None of the following exist in v0.1, by design:

- OpenAI, Anthropic, Claude Code, or Codex providers - only `FakeProvider`
- Multi-agent debate, planning, research, or architecture review
- Docker, PostgreSQL, Redis, a task queue, FastAPI, or any web UI
- Sandboxing. `writable_paths` / `read_only_paths` / `allowed_commands` may be
  declared in a task file, but **they are not enforced**. A validation command
  can currently read and write anywhere the user running FORGE can.
- Secret handling, budget and token metering, cost limits
- Git checkpointing and rollback
- Crash resume. `state.json` is written after every transition and contains
  enough to resume, but no resume command exists yet.

### Known limitation: `task_timeout_seconds` is not a hard wall-clock limit

`task_timeout_seconds` bounds **validation subprocesses**, and is checked
between attempts. It is **not** a hard wall-clock limit around provider
execution.

The provider runs inside the FORGE process as an ordinary call to
`implement()`. A provider that blocks forever cannot be forcibly interrupted;
the deadline is only observed once control returns. With the built-in
`FakeProvider` this is not reachable, but it becomes real as soon as providers
do meaningful work. Enforcing it properly requires running providers in a
separate process or thread with a kill path, which is deferred to a later phase.

### Known limitation: schema discovery

`schemas/task.schema.json` lives at the repository root and is not packaged.
FORGE finds it via `FORGE_TASK_SCHEMA`, then the repository root inferred from
the installed package, then `./schemas`. An editable install (`pip install -e`)
or running from the repository root therefore works; a non-editable install from
another directory does not. This is acceptable for v0.1 and should be resolved
by packaging the schema as package data when the schema set stabilises.

---

## İlk hedef

İlk pilotta sistem şu akışı kanıtlayacaktır:

1. Kullanıcı proje talebini verir.
2. Sistem proje anayasası ve kabul kriterleri oluşturur.
3. ChatGPT/OpenAI proje yönetimi ve hakemlik yapar.
4. Claude mimari eleştiri ve teknik değerlendirme yapar.
5. Kodlama ajanı projeyi uygular.
6. Bağımsız doğrulama katmanı testleri gerçekten çalıştırır.
7. Hatalar kök neden analiziyle düzeltilir.
8. Çalışan proje, test raporu ve dokümantasyonla teslim edilir.

## Önerilen roller

- OpenAI / ChatGPT: CEO, ürün yöneticisi, proje yöneticisi, final hakemi
- Claude: baş mimar, teknik eleştirmen, risk değerlendirici
- Claude Code veya Codex CLI: ana uygulayıcı
- Codex CLI veya ikinci sağlayıcı: bağımsız kod inceleyici
- Python orkestratör: durum makinesi, izinler, görev kuyruğu, maliyet ve denetim
- Docker + Git + CI: tarafsız doğrulama

## Başlangıç dosyaları

- `docs/PROJECT_CONSTITUTION.md`: değiştirilemez ve kullanıcı kontrollü kurallar
- `docs/PRODUCT_VISION.md`: ürün tanımı ve kapsam
- `docs/ARCHITECTURE.md`: sistem mimarisi
- `docs/ROADMAP.md`: fazlar ve teslim kapıları
- `docs/AUTHORIZATION_MODEL.md`: kullanıcı izin ve sorumluluk sistemi
- `docs/DEFINITION_OF_DONE.md`: tamamlanma kriterleri
- `prompts/CHATGPT_SYSTEM_PROMPT.md`: ChatGPT rol talimatı
- `prompts/CLAUDE_SYSTEM_PROMPT.md`: Claude rol talimatı
- `prompts/IMPLEMENTER_PROMPT.md`: kodlama ajanı talimatı
- `schemas/*.json`: ajanlar arası standart veri sözleşmeleri
- `config/project_defaults.yaml`: varsayılan proje politikaları
- `examples/pilot_bot/PROJECT_REQUEST.md`: ilk pilot örneği

## İlk çalışma sırası

1. `docs/PROJECT_CONSTITUTION.md` kullanıcı tarafından onaylanır.
2. API ve geliştirme ortamı hazırlanır.
3. Orkestratör iskeleti yazılır.
4. ChatGPT ve Claude sağlayıcı adaptörleri eklenir.
5. Tek görevlik kodlama/test döngüsü çalıştırılır.
6. İlk pilot bot baştan sona üretilir.
