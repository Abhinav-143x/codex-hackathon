import React, { useMemo, useState } from 'react';
import runsData from './data.json';
import './index.css';

const CHECK_ORDER = [
  ['coverage', 'Coverage'],
  ['consistency', 'Consistency'],
  ['test_exec', 'Test execution'],
  ['5w_evidence', '5W evidence'],
  ['proposer_escalation', 'Proposer escalation'],
  ['blind_spot', 'Blind spot'],
  ['invisible_unicode', 'Invisible Unicode'],
];

const W_FIELDS = [
  ['w_what', 'What changed'],
  ['w_why', 'Why needed'],
  ['w_impact', 'Who/what is impacted'],
  ['w_evidence', 'Where evidence points'],
  ['w_who', 'Who is affected'],
];

const SLOPPER_INTEGRATION = {
  status: 'Workflow present',
  path: '.github/workflows/slopper.yml',
  summary: 'Runs as a separate contributor-reputation signal. It is intentionally not blended into the Gate verdict.',
};

const DEMO_NOTES = {
  live_npm_cli_9473: {
    title: 'Registry tarball path validation',
    language: 'JavaScript',
    match: 'Matches the security intent; local adopted tests are not pinned for npm in this demo.',
    story: 'Merged upstream. PRGG separates maintainer acceptance from local proof.',
  },
  requests_7520: {
    title: 'Link header values with equals signs',
    language: 'Python',
    match: 'Matches the diff: split on the first equals sign in Link header parameters. Local focused test currently fails against current main.',
    story: 'Open external PR. Useful proof that local adopted tests can disagree with a plausible claim.',
  },
  requests_7543: {
    title: 'Project metadata URLs',
    language: 'Metadata',
    match: 'Matches the diff, but the proposer left the affected-user evidence incomplete.',
    story: 'Open external PR. Shows 5W grounding catching a weak non-code claim.',
  },
  cpython_153680: {
    title: 'Zipimport invalid UTF-8 handling',
    language: 'Python',
    match: 'Matches invalid UTF-8 handling in zipimport; escalated because validation/security-like claims need stronger proof.',
    story: 'Open external PR. Good language/runtime example with Unicode edge-case evidence.',
  },
  live_tensorflow_tensorflow_120484: {
    title: 'TFLite MaxUnpooling2D bounds validation',
    language: 'C++',
    match: 'Diff matches index validation before MaxUnpooling2D writes.',
    story: 'GitHub state is OPEN; PR body mentions a superseded PR, so internal/project landing must be described as a caveat, not as GitHub merged.',
  },
  live_protocolbuffers_protobuf_27848: {
    title: 'Ruby repeated enum getter null array',
    language: 'C/Ruby',
    match: 'Matches null repeated enum array handling, but GitHub closed without merge.',
    story: 'Closed upstream. Useful for explaining why closed is not automatically bad or good.',
  },
  live_protocolbuffers_protobuf_27852: {
    title: 'PHP repeated field and namespace validation',
    language: 'C++/PHP',
    match: 'Matches PHP repeated-field index and namespace validation hardening.',
    story: 'Open upstream. Shows security-ish claim routing to review instead of blind approval.',
  },
};

const CONNECTOR_CANDIDATES = [
  {
    repo: 'pallets/flask',
    number: 6013,
    state: 'MERGED',
    language: 'Python',
    title: 'autoescape selection uses case-insensitive comparison',
    size: '2 files, +6/-1',
    signal: 'Merged small maintainer PR; filename extension comparison now lowercases before matching.',
    url: 'https://github.com/pallets/flask/pull/6013',
  },
  {
    repo: 'pallets/flask',
    number: 6094,
    state: 'OPEN',
    language: 'Python',
    title: 'fix: handle IPv6 addresses in host parsing',
    size: '2 files, +8/-2',
    signal: 'Open PR; body claims bracket-aware IPv6 host parsing and tests.',
    url: 'https://github.com/pallets/flask/pull/6094',
  },
  {
    repo: 'vitejs/vite',
    number: 22893,
    state: 'MERGED',
    language: 'TypeScript',
    title: 'fix(ssr): scope switch-case declarations to the switch, not the function',
    size: 'TypeScript transform + tests',
    signal: 'Merged PR with review comments, approval, package preview, and ecosystem CI discussion.',
    url: 'https://github.com/vitejs/vite/pull/22893',
  },
  {
    repo: 'django/django',
    number: 21553,
    state: 'MERGED',
    language: 'Python',
    title: 'Fixed #37187, #37190 -- Pointed ModelAdmin warnings to the deprecated code.',
    size: 'Python utility + tests',
    signal: 'Merged PR with explicit AI-assistance disclosure and reviewer questions.',
    url: 'https://github.com/django/django/pull/21553',
  },
];

const DEFAULT_BYOK_CONFIG = {
  version: 1,
  provider_order: ['gemini', 'openrouter', 'openai', 'anthropic'],
  keys: {
    gemini: [''],
    openrouter: [''],
    openai: [''],
    anthropic: [''],
  },
  models: {
    gemini: {
      fast: ['gemini-flash-lite-latest', 'gemini-2.0-flash-lite', 'gemini-2.0-flash-lite-001', 'gemini-2.5-flash'],
      strong: ['gemini-flash-latest', 'gemini-3.5-flash', 'gemini-2.5-pro', 'gemini-2.5-flash'],
    },
    openrouter: {
      fast: ['openai/gpt-5.4-nano', 'openai/gpt-5.6-luna', 'openai/gpt-4o-mini'],
      strong: ['openai/gpt-5.6-luna', 'openai/gpt-5.6-terra', 'openai/gpt-4o'],
    },
    openai: {
      fast: ['gpt-5.4-nano', 'gpt-5.6-luna', 'gpt-4o-mini'],
      strong: ['gpt-5.6-luna', 'gpt-5.6-terra', 'gpt-4o'],
    },
    anthropic: {
      fast: ['claude-3-haiku-20240307'],
      strong: ['claude-3-5-sonnet-20241022'],
    },
  },
};

const PROVIDER_LABELS = {
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  openai: 'OpenAI',
  anthropic: 'Anthropic',
};

function asList(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

function providerKeyPool(config, provider) {
  const keys = config.keys || {};
  const raw = keys[provider];
  let pool = [];
  if (Array.isArray(raw)) {
    pool = raw;
  } else if (typeof raw === 'string') {
    pool = [raw];
  }

  let index = 1;
  while (Object.prototype.hasOwnProperty.call(keys, `${provider}_${index}`)) {
    pool.push(keys[`${provider}_${index}`]);
    index += 1;
  }

  const plural = keys[`${provider}_keys`];
  if (Array.isArray(plural)) pool.push(...plural);

  const cleaned = pool.map((value) => String(value || ''));
  return cleaned.length ? cleaned : [''];
}

function normalizeByokConfig(parsed) {
  const merged = {
    ...DEFAULT_BYOK_CONFIG,
    ...parsed,
    keys: { ...DEFAULT_BYOK_CONFIG.keys, ...(parsed.keys || {}) },
    models: { ...DEFAULT_BYOK_CONFIG.models, ...(parsed.models || {}) },
  };

  const normalizedKeys = {};
  Object.keys(PROVIDER_LABELS).forEach((provider) => {
    normalizedKeys[provider] = providerKeyPool(merged, provider);
  });
  merged.keys = normalizedKeys;
  return merged;
}

function verdictOf(run) {
  return run?.verdict?.verdict || 'unknown';
}

function noteFor(run) {
  return DEMO_NOTES[run?.sample_name] || {
    title: prTitle(run),
    language: inferLanguage(run),
    match: run?.verdict?.failing_checks?.length ? 'Saved run needs human review before a claim can be trusted.' : 'Saved run has no additional demo note.',
    story: run?.pr_url ? 'Saved live PR run.' : 'Synthetic/local evidence sample.',
  };
}

function inferLanguage(run) {
  const text = `${run?.claim?.file || ''} ${run?.diff_text || ''}`.toLowerCase();
  if (text.includes('.py')) return 'Python';
  if (text.includes('.ts') || text.includes('typescript')) return 'TypeScript';
  if (text.includes('.js')) return 'JavaScript';
  if (text.includes('.cc') || text.includes('.cpp')) return 'C++';
  if (text.includes('.c')) return 'C';
  if (text.includes('.rb')) return 'Ruby';
  if (text.includes('.php')) return 'PHP';
  return 'Mixed';
}

function commandFor(target) {
  const safeTarget = target.trim() || 'https://github.com/owner/repo/pull/123';
  return `.\\.venv\\Scripts\\prgg.exe check ${safeTarget}`;
}

function formatDate(value) {
  if (!value) return 'unknown';
  try {
    return new Date(value).toLocaleString([], {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return String(value).slice(0, 16);
  }
}

function prTitle(run) {
  const firstLine = String(run?.pr_description || '').split('\n').find(Boolean);
  return firstLine || run?.sample_name || 'Untitled PR analysis';
}

function displayTitle(run) {
  return noteFor(run).title || prTitle(run);
}

function repoLabel(run) {
  const url = run?.pr_url || '';
  const match = url.match(/github\.com\/([^/]+\/[^/]+)\/pull\/(\d+)/i);
  if (match) return `${match[1]} #${match[2]}`;
  return run?.sample_name || 'local sample';
}

function diffStats(diff) {
  return String(diff || '').split('\n').reduce(
    (acc, line) => {
      if (line.startsWith('diff --git ')) {
        const match = line.match(/^diff --git a\/(.+?) b\//);
        acc.files.add(match?.[1] || line);
      } else if (!acc.files.size && line.startsWith('--- a/')) {
        acc.files.add(line.replace('--- a/', ''));
      }
      if (line.startsWith('+') && !line.startsWith('+++')) acc.additions += 1;
      if (line.startsWith('-') && !line.startsWith('---')) acc.deletions += 1;
      return acc;
    },
    { files: new Set(), additions: 0, deletions: 0 },
  );
}

function decisionCopy(run, checks) {
  const verdict = verdictOf(run);
  const failing = run?.verdict?.failing_checks || [];
  if (verdict === 'grounded') {
    return 'The Gate found the claim grounded in changed lines, matching symbols, executable evidence, and blind-spot checks.';
  }
  if (verdict === 'ungrounded') {
    return `The Gate rejected the claim because ${failing.join(', ') || 'one or more checks'} contradicted the PR evidence.`;
  }
  const missing = failing.length ? failing.join(', ') : Object.entries(checks).filter(([, result]) => !result?.pass).map(([name]) => name).join(', ');
  return `The Gate routed this to human review because ${missing || 'required evidence'} is not fully proven by the saved run.`;
}

function upstreamSignal(run) {
  const state = String(run?.state || '').toUpperCase();
  if (state === 'MERGED') return { label: 'Merged upstream', tone: 'merged' };
  if (state === 'OPEN') return { label: 'Open upstream', tone: 'open' };
  if (state === 'CLOSED') return { label: 'Closed upstream', tone: 'closed' };
  return { label: 'No upstream state', tone: 'unknown' };
}

function localProofSignal(run) {
  const reason = String(run?.verdict?.checks?.test_exec?.reason || run?.gate?.test_exec?.reason || '');
  if (reason.includes('[ADOPTED]') && /passed/i.test(reason)) {
    return { label: 'Local adopted test passed', tone: 'grounded' };
  }
  if (reason.includes('[ADOPTED]') && /failed/i.test(reason)) {
    return { label: 'Local adopted test failed', tone: 'ungrounded' };
  }
  if (/no repo-specific test runner|placeholder|stub pass|mock/i.test(reason)) {
    return { label: 'Local test not adopted', tone: 'needs-review' };
  }
  return { label: 'Local test signal unknown', tone: 'unknown' };
}

function MarkdownBlock({ text }) {
  const lines = String(text || '').split('\n');
  const nodes = [];
  let list = [];
  let code = [];
  let inCode = false;

  function flushList() {
    if (list.length) {
      nodes.push(<ul key={`ul-${nodes.length}`}>{list.map((item, index) => <li key={`${index}-${item.slice(0, 12)}`}>{item}</li>)}</ul>);
      list = [];
    }
  }

  function flushCode() {
    if (code.length) {
      nodes.push(<pre key={`code-${nodes.length}`}>{code.join('\n')}</pre>);
      code = [];
    }
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('```')) {
      if (inCode) {
        inCode = false;
        flushCode();
      } else {
        flushList();
        inCode = true;
      }
      return;
    }
    if (inCode) {
      code.push(line);
      return;
    }
    if (!trimmed) {
      flushList();
      return;
    }
    if (trimmed.startsWith('## ')) {
      flushList();
      nodes.push(<h4 key={`h-${index}`}>{trimmed.replace(/^##\s+/, '')}</h4>);
      return;
    }
    if (/^[-*]\s+/.test(trimmed)) {
      list.push(trimmed.replace(/^[-*]\s+/, ''));
      return;
    }
    flushList();
    nodes.push(<p key={`p-${index}`}>{trimmed}</p>);
  });
  flushList();
  flushCode();

  return <div className="markdown-body">{nodes.length ? nodes : <p>No PR body captured.</p>}</div>;
}

function CheckRow({ name, label, result }) {
  const hasResult = Boolean(result);
  const pass = Boolean(result?.pass);
  return (
    <div className={`check-row ${!hasResult ? 'muted-row' : ''}`}>
      <span className={`check-mark ${pass ? 'pass' : 'fail'}`}>{pass ? 'PASS' : hasResult ? 'FAIL' : 'N/A'}</span>
      <div>
        <strong>{label}</strong>
        <p>{result?.reason || `${name} did not report a reason.`}</p>
      </div>
    </div>
  );
}

function DiffPreview({ diff }) {
  const lines = String(diff || '').split('\n').slice(0, 120);
  return (
    <pre className="diff-preview">
      {lines.map((line, index) => {
        const kind = line.startsWith('+') && !line.startsWith('+++')
          ? 'add'
          : line.startsWith('-') && !line.startsWith('---')
            ? 'del'
            : '';
        return (
          <span className={kind} key={`${index}-${line.slice(0, 12)}`}>
            {line}
            {'\n'}
          </span>
        );
      })}
    </pre>
  );
}

function EvidencePanel({ run }) {
  if (!run) {
    return (
      <section className="evidence-panel empty-state">
        <p>No run selected.</p>
      </section>
    );
  }

  const gate = run.gate || {};
  const checks = run.verdict?.checks || {};
  const mergedChecks = { ...gate, ...checks };
  const verdict = verdictOf(run);
  const stats = diffStats(run.diff_text);
  const failing = run.verdict?.failing_checks || [];
  const reasons = run.verdict?.reasons || [];
  const prUrl = run.pr_url || '';

  return (
    <section className="evidence-panel">
      <div className="pr-header">
        <div className="pr-title-block">
          <span className="eyebrow">{repoLabel(run)}</span>
          <h2>{displayTitle(run)}</h2>
          <div className="pr-meta">
            <span className={`verdict verdict-${verdict}`}>{verdict}</span>
            <span>{formatDate(run.run_timestamp)}</span>
            <span>{run.elapsed_s ?? '0'}s</span>
            {run.state && <span>{run.state}</span>}
          </div>
        </div>
        {prUrl && (
          <a className="ghost-link" href={prUrl} rel="noreferrer" target="_blank">Open on GitHub</a>
        )}
      </div>

      <div className="conversation-card decision-card">
        <div className="avatar verdict-avatar">GG</div>
        <div className="comment-body">
          <div className="comment-head">
            <strong>PR Grounding Gate decision</strong>
            <span>No LLM decides this verdict</span>
          </div>
          <p>{decisionCopy(run, mergedChecks)}</p>
          {reasons.length > 0 && (
            <ul className="reason-list">
              {reasons.map((reason, index) => (
                <li key={`${index}-${reason.slice(0, 24)}`}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="signal-grid">
        <div>
          <span>Upstream</span>
          <strong className={`state-pill state-${upstreamSignal(run).tone}`}>{upstreamSignal(run).label}</strong>
        </div>
        <div>
          <span>Local proof</span>
          <strong className={`verdict verdict-${localProofSignal(run).tone}`}>{localProofSignal(run).label}</strong>
        </div>
        <div>
          <span>Claim match</span>
          <p>{noteFor(run).match}</p>
        </div>
      </div>

      <div className="pr-tabs" aria-label="Selected analysis sections">
        <span className="active">Conversation</span>
        <span>Checks {Object.keys(mergedChecks).length}</span>
        <span>Files changed {stats.files.size || 1}</span>
      </div>

      <div className="status-summary">
        <div>
          <span>Changed</span>
          <strong>{stats.files.size || 1} file{(stats.files.size || 1) === 1 ? '' : 's'}</strong>
        </div>
        <div>
          <span>Additions</span>
          <strong className="add-stat">+{stats.additions}</strong>
        </div>
        <div>
          <span>Deletions</span>
          <strong className="del-stat">-{stats.deletions}</strong>
        </div>
        <div>
          <span>Failed / missing</span>
          <strong>{failing.length || 0}</strong>
        </div>
      </div>

      <div className="claim-grid">
        <div>
          <span>Claim file</span>
          <strong>{run.claim?.file || 'unknown'}</strong>
        </div>
        <div>
          <span>Claim lines</span>
          <strong>{run.claim?.line_range || 'unknown'}</strong>
        </div>
        <div>
          <span>Claim type</span>
          <strong>{run.claim?.bug_type || 'unknown'}</strong>
        </div>
        <div>
          <span>Confidence</span>
          <strong>{run.claim?.confidence ?? 'unknown'}</strong>
        </div>
      </div>

      <section className="five-w">
        <div className="subhead">Claim 5W</div>
        <div className="five-w-grid">
          {W_FIELDS.map(([key, label]) => (
            <div className="w-card" key={key}>
              <span>{label}</span>
              <p>{run.claim?.[key] || 'Not supplied by proposer.'}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pr-body-panel">
        <div className="subhead">Fetched PR body</div>
        <MarkdownBlock text={run.pr_description} />
      </section>

      <div className="explanation-box">
        <strong>Reviewer-readable explanation</strong>
        <p>{run.explanation || 'No explanation recorded.'}</p>
      </div>

      <div className="checks-stack">
        {CHECK_ORDER.map(([name, label]) => (
          <CheckRow key={name} name={name} label={label} result={mergedChecks[name]} />
        ))}
      </div>

      <div className="diff-shell">
        <div className="subhead">Diff preview</div>
        <DiffPreview diff={run.diff_text} />
      </div>
    </section>
  );
}

function RunList({ runs, selectedId, onSelect }) {
  return (
    <section className="run-list">
      {runs.map((run) => {
        const verdict = verdictOf(run);
        const selected = run.sample_name === selectedId;
        const failing = run.verdict?.failing_checks || [];
        return (
          <button
            className={`run-row ${selected ? 'selected' : ''}`}
            aria-current={selected ? 'true' : undefined}
            key={run.sample_name}
            onClick={() => onSelect(run.sample_name)}
            type="button"
          >
            <span className={`status-dot dot-${verdict}`} />
            <span className="run-main">
              <strong>{run.sample_name}</strong>
              <small>{prTitle(run)}</small>
            </span>
            <span className="run-side">
              <span className={`verdict verdict-${verdict}`}>{verdict}</span>
              <small>{failing.length ? failing.join(', ') : formatDate(run.run_timestamp)}</small>
            </span>
          </button>
        );
      })}
    </section>
  );
}

function DemoBoard({ runs, selectedRun, onSelect }) {
  const liveRuns = runs.filter((run) => run.pr_url);
  const byState = ['MERGED', 'OPEN', 'CLOSED'].map((state) => ({
    state,
    runs: liveRuns.filter((run) => String(run.state || '').toUpperCase() === state),
  }));
  const verdictCounts = liveRuns.reduce((acc, run) => {
    acc[verdictOf(run)] = (acc[verdictOf(run)] || 0) + 1;
    return acc;
  }, {});

  return (
    <>
      <section className="demo-hero">
        <div>
          <span className="eyebrow">Demo board</span>
          <h1>Real PRs, grounded decisions.</h1>
          <p>Use this screen for the pitch: saved runs on the left, GitHub-like evidence on the right, and connector-verified outside PRs below for breadth.</p>
        </div>
        <div className="demo-kpis">
          <div><span>Live runs</span><strong>{liveRuns.length}</strong></div>
          <div><span>Needs review</span><strong>{verdictCounts['needs-review'] || 0}</strong></div>
          <div><span>External candidates</span><strong>{CONNECTOR_CANDIDATES.length}</strong></div>
        </div>
      </section>

      <section className="demo-layout">
        <aside className="demo-groups">
          {byState.map((group) => (
            <div className="demo-group" key={group.state}>
              <div className="demo-group-title">
                <strong>{group.state}</strong>
                <span>{group.runs.length}</span>
              </div>
              {group.runs.map((run) => {
                const note = noteFor(run);
                const selected = selectedRun?.sample_name === run.sample_name;
                return (
                  <button className={`demo-card ${selected ? 'selected' : ''}`} key={run.sample_name} onClick={() => onSelect(run.sample_name)} type="button">
                    <span className="demo-card-top">
                      <span className={`verdict verdict-${verdictOf(run)}`}>{verdictOf(run)}</span>
                      <span>{note.language}</span>
                    </span>
                    <strong>{displayTitle(run)}</strong>
                    <small>{repoLabel(run)}</small>
                    <p>{note.story}</p>
                  </button>
                );
              })}
            </div>
          ))}
        </aside>
        <EvidencePanel run={selectedRun} />
      </section>

      <section className="candidate-band">
        <div className="candidate-head">
          <div>
            <span className="eyebrow">GitHub connector fetch</span>
            <h2>Diverse outside PRs for stage backup</h2>
          </div>
          <p>Fetched through the GitHub integration after the unauthenticated API hit rate limits.</p>
        </div>
        <div className="candidate-grid">
          {CONNECTOR_CANDIDATES.map((item) => (
            <a className="candidate-card" href={item.url} key={item.url} rel="noreferrer" target="_blank">
              <span className="candidate-meta">
                <span className={`state-pill state-${item.state.toLowerCase()}`}>{item.state}</span>
                <span>{item.language}</span>
                <span>{item.size}</span>
              </span>
              <strong>{item.repo} #{item.number}</strong>
              <h3>{item.title}</h3>
              <p>{item.signal}</p>
            </a>
          ))}
        </div>
      </section>
    </>
  );
}

function Analyzer({ runs, selectedRun, onSelect }) {
  const [target, setTarget] = useState('https://github.com/psf/requests/pull/7520');
  const [copied, setCopied] = useState(false);

  const matchingRun = useMemo(() => {
    const wanted = target.trim();
    if (!wanted) return null;
    return runs.find((run) => run.pr_url === wanted || run.sample_name === wanted) || null;
  }, [runs, target]);

  const command = commandFor(target);

  async function copyCommand() {
    setCopied(false);
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  return (
    <>
      <section className="evaluator">
        <div className="evaluator-copy">
          <span className="eyebrow">Analyze PR</span>
          <h1>Paste one PR. Run one command.</h1>
          <p>This is the clean demo flow for a fresh public PR. The browser does not hold provider secrets; the CLI reads BYOK keys from the local keyring.</p>
        </div>

        <div className="analyzer-stack">
          <div className="input-rail">
            <input
              aria-label="Pull request URL"
              onChange={(event) => setTarget(event.target.value)}
              placeholder="https://github.com/owner/repo/pull/123"
              spellCheck="false"
              value={target}
            />
            {matchingRun ? (
              <button type="button" onClick={() => onSelect(matchingRun.sample_name)}>Open saved run</button>
            ) : (
              <button type="button" onClick={copyCommand}>{copied ? 'Copied' : 'Copy CLI command'}</button>
            )}
          </div>

          <code className="command-line">{command}</code>

          <div className="integration-callout">
            <span>Slopper</span>
            <strong>{SLOPPER_INTEGRATION.status}</strong>
            <p>{SLOPPER_INTEGRATION.summary}</p>
          </div>
        </div>
      </section>

      <section className="workspace analyzer-workspace">
        <aside className="left-pane">
          <RunList runs={runs.filter((run) => run.pr_url)} selectedId={selectedRun?.sample_name} onSelect={onSelect} />
        </aside>
        <EvidencePanel run={selectedRun} />
      </section>
    </>
  );
}

function ConfigBuilder() {
  const [config, setConfig] = useState(DEFAULT_BYOK_CONFIG);
  const [notice, setNotice] = useState('');
  const importCommand = '.\\.venv\\Scripts\\prgg.exe config import .\\prgg-byok-config.json';

  function updateKeyPool(provider, index, value) {
    setConfig((current) => ({
      ...current,
      keys: {
        ...current.keys,
        [provider]: providerKeyPool(current, provider).map((item, itemIndex) => (
          itemIndex === index ? value : item
        )),
      },
    }));
  }

  function addKeySlot(provider) {
    setConfig((current) => ({
      ...current,
      keys: {
        ...current.keys,
        [provider]: [...providerKeyPool(current, provider), ''],
      },
    }));
  }

  function removeKeySlot(provider, index) {
    setConfig((current) => {
      const nextPool = providerKeyPool(current, provider).filter((_, itemIndex) => itemIndex !== index);
      return {
        ...current,
        keys: {
          ...current.keys,
          [provider]: nextPool.length ? nextPool : [''],
        },
      };
    });
  }

  function updateModels(provider, tier, value) {
    setConfig((current) => ({
      ...current,
      models: {
        ...current.models,
        [provider]: {
          ...current.models[provider],
          [tier]: asList(value),
        },
      },
    }));
  }

  function updateOrder(value) {
    const provider_order = asList(value).filter((provider) => PROVIDER_LABELS[provider]);
    setConfig((current) => ({ ...current, provider_order }));
  }

  function readFile(file) {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result || '{}'));
        setConfig(normalizeByokConfig(parsed));
        setNotice(`Loaded ${file.name}`);
      } catch (error) {
        setNotice(`Could not parse ${file.name}: ${error.message}`);
      }
    };
    reader.readAsText(file);
  }

  function handleDrop(event) {
    event.preventDefault();
    const file = event.dataTransfer.files?.[0];
    if (file) readFile(file);
  }

  function downloadConfig() {
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'prgg-byok-config.json';
    link.click();
    URL.revokeObjectURL(url);
    setNotice('Downloaded prgg-byok-config.json');
  }

  async function copyImportCommand() {
    try {
      await navigator.clipboard.writeText(importCommand);
      setNotice('Copied CLI import command');
    } catch {
      setNotice('Copy failed; command is visible below');
    }
  }

  return (
    <section className="byok-shell">
      <div className="byok-hero">
        <div>
          <span className="eyebrow">BYOK config</span>
          <h1>Build the model fallback file.</h1>
          <p>Keys stay in this browser until you download the JSON. The CLI imports it into OS keyring and keeps model settings in <code>~/.prgg/config.json</code>.</p>
        </div>
        <div
          className="drop-zone"
          onDragOver={(event) => event.preventDefault()}
          onDrop={handleDrop}
        >
          <strong>Drop config JSON</strong>
          <span>or use the defaults below</span>
        </div>
      </div>

      <div className="byok-grid">
        <section className="config-panel">
          <div className="subhead">Provider order</div>
          <input
            aria-label="Provider order"
            onChange={(event) => updateOrder(event.target.value)}
            value={config.provider_order.join(', ')}
          />
          <div className="provider-stack">
            {Object.keys(PROVIDER_LABELS).map((provider) => (
              <div className="provider-card" key={provider}>
                <div className="provider-title">
                  <strong>{PROVIDER_LABELS[provider]}</strong>
                  <span>{config.provider_order.includes(provider) ? 'enabled' : 'fallback only'}</span>
                </div>
                <div className="key-pool">
                  <div className="key-pool-title">
                    <span>Key pool</span>
                    <button type="button" onClick={() => addKeySlot(provider)}>Add key</button>
                  </div>
                  <div className="key-pool-grid">
                    {providerKeyPool(config, provider).map((value, index) => (
                      <label key={`${provider}-${index}`}>
                        Key {index + 1}
                        <span className="key-input-row">
                          <input
                            onChange={(event) => updateKeyPool(provider, index, event.target.value)}
                            placeholder={`${provider} key ${index + 1}`}
                            type="password"
                            value={value}
                          />
                          <button
                            aria-label={`Remove ${provider} key ${index + 1}`}
                            disabled={providerKeyPool(config, provider).length === 1}
                            onClick={() => removeKeySlot(provider, index)}
                            type="button"
                          >
                            -
                          </button>
                        </span>
                      </label>
                    ))}
                  </div>
                </div>
                <label>
                  Fast models
                  <textarea
                    onChange={(event) => updateModels(provider, 'fast', event.target.value)}
                    rows="2"
                    value={(config.models[provider]?.fast || []).join(', ')}
                  />
                </label>
                <label>
                  Strong models
                  <textarea
                    onChange={(event) => updateModels(provider, 'strong', event.target.value)}
                    rows="2"
                    value={(config.models[provider]?.strong || []).join(', ')}
                  />
                </label>
              </div>
            ))}
          </div>
        </section>

        <section className="config-panel preview-panel">
          <div className="subhead">Download and import</div>
          <pre className="json-preview">{JSON.stringify(config, null, 2)}</pre>
          <div className="button-row">
            <button type="button" onClick={downloadConfig}>Download JSON</button>
            <button type="button" onClick={copyImportCommand}>Copy import command</button>
          </div>
          <code className="command-line">{importCommand}</code>
          {notice && <p className="notice-line">{notice}</p>}
        </section>
      </div>
    </section>
  );
}

function App() {
  const runs = useMemo(() => {
    return [...runsData].sort((a, b) => {
      return String(b.run_timestamp || '').localeCompare(String(a.run_timestamp || ''));
    });
  }, []);

  const [selectedId, setSelectedId] = useState('live_npm_cli_9473');
  const [view, setView] = useState('demo');

  const selectedRun = runs.find((run) => run.sample_name === selectedId) || runs.find((run) => run.pr_url) || runs[0];

  return (
    <main className="app-shell">
      <nav className="top-tabs" aria-label="Primary">
        <button className={view === 'demo' ? 'active' : ''} onClick={() => setView('demo')} type="button">Demo Board</button>
        <button className={view === 'analyze' ? 'active' : ''} onClick={() => setView('analyze')} type="button">Analyze PR</button>
        <button className={view === 'byok' ? 'active' : ''} onClick={() => setView('byok')} type="button">BYOK Config</button>
      </nav>

      {view === 'byok' ? <ConfigBuilder /> : view === 'demo' ? (
        <DemoBoard runs={runs} selectedRun={selectedRun} onSelect={setSelectedId} />
      ) : (
        <Analyzer runs={runs} selectedRun={selectedRun} onSelect={setSelectedId} />
      )}
    </main>
  );
}

export default App;
