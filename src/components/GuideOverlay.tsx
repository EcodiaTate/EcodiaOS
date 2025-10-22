'use client'

import { useEffect, useState } from 'react'
import { useModeStore } from '@/stores/useModeStore'
import { BackToEcodiaButton, BackToHubButton } from '@/components/ui'

const glitchChars = ['@', '#', '∿', '▞', '█', '▓', '▒', '░', '⚠', '∆', '*', '%', '&', 'π', '¤', '⍉']

function useGlitchText(targetText: string, intervalMs = 50, lockDelay = 500) {
  const [displayText, setDisplayText] = useState<string[]>(Array(targetText.length).fill(''))
  useEffect(() => {
    const timeouts: NodeJS.Timeout[] = []
    targetText.split('').forEach((char, i) => {
      let current = 0
      const t = setInterval(() => {
        setDisplayText(prev => {
          const updated = [...prev]
          updated[i] = glitchChars[Math.floor(Math.random() * glitchChars.length)]
          return updated
        })
        current++
        if (current > lockDelay / intervalMs) {
          clearInterval(t)
          setDisplayText(prev => {
            const updated = [...prev]
            updated[i] = char
            return updated
          })
        }
      }, intervalMs)
      timeouts.push(t)
    })
    return () => timeouts.forEach(clearInterval)
  }, [targetText, intervalMs, lockDelay])
  return displayText.join('')
}

interface QuestionWithEventID {
  id: number
  text: string
  style: string
  topic?: string
  response_type?: 'choice' | 'slider' | 'text'
  event_id: string
}

export default function GuideOverlay() {
  const setMode = useModeStore(s => s.setMode)

  const titleText = useGlitchText('Shape the Future...')
  const subText = useGlitchText('Guide the mind of Ecodia', 50, 500)

  const [soulNode, setSoulNode] = useState<string | null>(null)
  const [questions, setQuestions] = useState<QuestionWithEventID[]>([])
  const [answers, setAnswers] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState<Record<number, boolean>>({})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>('')

  useEffect(() => {
    // Load soul soul safely on client
    try {
      const saved = localStorage.getItem('soulNode')
      if (saved) setSoulNode(saved)
    } catch {}
  }, [])

  useEffect(() => {
    async function fetchQuestions() {
      try {
        const res = await fetch('http://localhost:8000/evo/questions')
        const data = await res.json()
        setQuestions(data?.questions || [])
      } catch (err) {
        console.error('[GuideOverlay] Failed to fetch questions:', err)
        setError('Failed to load questions.')
      } finally {
        setLoading(false)
      }
    }
    fetchQuestions()
  }, [])

  const handleAnswerChange = (index: number, value: string) => {
    setAnswers(prev => ({ ...prev, [index]: value }))
  }

  const handleSubmit = async (index: number) => {
    const question = questions[index]
    const answer = answers[index]
    if (!soulNode) {
      setError('No soul found. Please return and enter your soul soul.')
      return
    }
    if (!question?.event_id) {
      console.error('[GuideOverlay] Missing event_id on question:', question)
      return
    }

    setSubmitted(prev => ({ ...prev, [index]: true }))
    try {
      await fetch('http://localhost:8000/evo/answers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          soul_node: soulNode,
          answer,
          question_event_id: question.event_id,
        }),
      })
    } catch (err) {
      console.error('[GuideOverlay] Failed to submit answer:', err)
    }
  }

  const renderResponseInput = (q: QuestionWithEventID, index: number) => {
    switch (q.response_type) {
      case 'choice':
        return (
          <select
            className="field select"
            onChange={e => handleAnswerChange(index, e.target.value)}
            value={answers[index] || ''}
          >
            <option value="">Select an option…</option>
            <option value="agree">Agree</option>
            <option value="neutral">Neutral</option>
            <option value="disagree">Disagree</option>
          </select>
        )
      case 'slider':
        return (
          <div className="mt-3">
            <input
              type="range"
              min="-5"
              max="5"
              value={answers[index] ?? '0'}
              onChange={e => handleAnswerChange(index, e.target.value)}
              className="w-full accent-[#F4D35E]"
            />
            <div className="text-[.8rem] text-[rgba(233,244,236,.9)] text-right mt-1">
              {answers[index] ?? 0}
            </div>
          </div>
        )
      case 'text':
      default:
        return (
          <textarea
            rows={3}
            placeholder="Your thoughts…"
            value={answers[index] || ''}
            onChange={e => handleAnswerChange(index, e.target.value)}
            className="field"
          />
        )
    }
  }

  const renderStyledQuestion = (q: QuestionWithEventID, i: number) => {
    const styleKey = (q.style || 'default').toLowerCase()
    return (
      <article key={i} role="listitem" className={`qcard ${styleKey}`}>
        <div className="qhead">
          <div className="qtitle">{q.text}</div>
          {q.topic && <div className="qtag">{q.topic}</div>}
        </div>

        {renderResponseInput(q, i)}

        {submitted[i] ? (
          <div className="ack">✔ Answered</div>
        ) : (
          <button
            onClick={() => handleSubmit(i)}
            className="btn contribute"
            title="Contribute your answer"
          >
            Contribute
          </button>
        )}
      </article>
    )
  }

  return (
    <div className="absolute inset-0 z-40 flex flex-col items-center justify-start px-3 pt-6 sm:px-6 sm:pt-10 isolate">
      {/* Fonts */}
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
      <link
        href="https://fonts.googleapis.com/css2?family=Comfortaa:wght@300;400;700&family=Fjalla+One&display=swap"
        rel="stylesheet"
      />

      <BackToHubButton />
      <BackToEcodiaButton />

      {/* Panel */}
      <section id="guide-overlay" className="panel pointer-events-auto" aria-label="Guide Ecodia">
        <h1 className="title">{titleText}</h1>
        <p className="lead">{subText}</p>

        {/* Missing soul state */}
        {!soulNode && (
          <div className="emptystate">
            <p className="emptylead">You’ll need your constellation soul to guide Ecodia.</p>
            <div className="actions">
              <button className="btn" onClick={() => setMode('constellation')}>Create my soul</button>
              <button className="btn secondary" onClick={() => setMode('return')}>I’m returning</button>
            </div>
          </div>
        )}

        {/* Questions */}
        {soulNode && (
          <>
            {loading ? (
              <p className="muted">Summoning questions from Evo…</p>
            ) : error ? (
              <p className="muted">{error}</p>
            ) : questions.length === 0 ? (
              <p className="muted">Evo found no unresolved thoughts today.</p>
            ) : (
              <div className="qlist" role="list">
                {questions.map(renderStyledQuestion)}
              </div>
            )}
          </>
        )}
      </section>

      {/* Scoped styles */}
      <style>{`
        #guide-overlay, .panel, .qcard, .btn, .field {
          --black:#000; --white:#fff;
          --g1:#396041; --g2:#7FD069; --g3:#F4D35E;
          --ink:#e9f4ec; --muted:rgba(255,255,255,.78);
          --edge:rgba(255,255,255,.10);
          --card:rgba(255,255,255,.06);
          --card-strong: rgba(14,20,16,.92);
          --shadow:0 10px 28px rgba(0,0,0,.45);
          font-family:"Comfortaa", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
          color:var(--ink);
        }

        .panel{
          width: clamp(320px, 92vw, 980px);
          margin: 0 auto;
          padding: clamp(18px, 4.8vw, 28px);
          border-radius:20px;
          border:1px solid var(--edge);
          background:
            linear-gradient(180deg, rgba(14,20,16,.80), rgba(14,20,16,.66)) padding-box,
            radial-gradient(120% 160% at 20% 0%, rgba(127,208,105,.12), transparent 55%) padding-box,
            radial-gradient(140% 160% at 100% 100%, rgba(244,211,94,.10), transparent 60%) padding-box;
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.03), var(--shadow);
          backdrop-filter: blur(10px) saturate(1.02);
          text-align: center;
        }
        .panel::after{
          content:""; position:absolute; inset:0; pointer-events:none; border-radius:inherit;
          background:
            linear-gradient(115deg, transparent 0%, rgba(255,255,255,.12) 14%, rgba(255,255,255,.06) 22%, transparent 30%),
            radial-gradient(600px 140px at 22% -10%, rgba(127,208,105,.10), transparent 60%),
            radial-gradient(480px 160px at 120% 120%, rgba(244,211,94,.08), transparent 70%);
          mix-blend-mode: screen; opacity:.9;
        }

        .title{
          font-family:"Fjalla One","Comfortaa",ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
          color: var(--g3);
          font-size: clamp(1.6rem, 5.8vw, 2.2rem);
          margin: 0 0 .4rem;
          letter-spacing:.2px;
        }
        .lead{
          color: var(--muted);
          font-size: clamp(1rem, 2.6vw, 1.1rem);
          margin: 0 auto .9rem;
        }
        .muted{ color: rgba(233,244,236,.7); }

        .emptystate{ margin: .4rem auto .4rem; }
        .emptylead{ color: rgba(233,244,236,.85); margin-bottom: .7rem; }
        .actions{ display:flex; gap:.6rem; justify-content:center; flex-wrap:wrap; }

        .qlist{
          margin-top: .6rem;
          display: grid;
          gap: .7rem;
          grid-template-columns: 1fr;
          max-height: 65vh; overflow-y:auto; padding-right: .25rem; text-align:left;
        }
        @media (min-width: 900px){
          .qlist{ grid-template-columns: 1fr 1fr; }
        }
        .qlist::-webkit-scrollbar{ width: 0; height: 0; }

        .qcard{
          border-radius:16px;
          border:1px solid var(--edge);
          background:
            linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04)) padding-box,
            rgba(14,20,16,.35);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.03);
          padding: clamp(12px, 2.6vw, 16px);
          display:flex; flex-direction:column; gap:.55rem;
          transition: transform .2s ease, filter .2s ease;
        }
        .qcard:hover{ transform: translateY(-1px); filter:saturate(1.02); }

        .qhead{ display:flex; align-items:flex-start; justify-content:space-between; gap:.6rem; }
        .qtitle{ font-size:1.02rem; font-weight:600; color:var(--ink); }
        .qtag{
          align-self:flex-start;
          font-size:.72rem; letter-spacing:.25px; text-transform:uppercase;
          color:rgba(233,244,236,.85);
          background: rgba(255,255,255,.06);
          border:1px solid var(--edge);
          border-radius:999px; padding:.18rem .5rem;
        }

        /* Style variants (gentle accenting) */
        .qcard.bold{ box-shadow: inset 0 0 0 1px rgba(244,211,94,.15); }
        .qcard.italic{ font-style: italic; }
        .qcard.ghost{ color: rgba(233,244,236,.78); background: rgba(255,255,255,.04); }
        .qcard.highlight{ box-shadow: inset 0 0 0 1px rgba(244,211,94,.25); }
        .qcard.whisper{ opacity:.92; }
        .qcard.default{}

        .field{
          width: 100%;
          padding: .7rem .9rem;
          border-radius:12px;
          color: var(--ink);
          border:1px solid var(--edge);
          background:
            linear-gradient(180deg, rgba(255,255,255,.08), rgba(255,255,255,.04)) padding-box,
            rgba(14,20,16,.35);
          box-shadow: inset 0 0 0 1px rgba(255,255,255,.03);
          backdrop-filter: blur(8px) saturate(1.02);
          font-size:.95rem;
        }
        .field::placeholder{ color: rgba(233,244,236,.6); }
        .field:focus{ outline:none; }
        .field:focus-visible{ box-shadow: 0 0 0 2px #000, 0 0 0 5px rgba(127,208,105,.65); }
        .select{ color: #111; background: #f9f9f6; border-color: rgba(0,0,0,.15); }

        .ack{ margin-top:.5rem; color:#7FD069; font-weight:600; font-size:.95rem; }

        .btn{
          position:relative; display:inline-flex; align-items:center; justify-content:center; gap:.5rem;
          padding:.75rem 1rem; border-radius:999px; color:#fff; text-decoration:none;
          border:1px solid rgba(0,0,0,.4);
          box-shadow: var(--shadow), inset 0 0 0 1px rgba(255,255,255,.06);
          overflow:hidden; transition: transform .2s ease, box-shadow .2s ease, filter .2s ease; isolation:isolate;
          cursor:pointer;
          background:
            radial-gradient(120% 140% at 15% 15%, rgba(255,255,255,.12) 0%, transparent 55%),
            linear-gradient(135deg, var(--g1) 0%, var(--g2) 60%, var(--g3) 100%);
        }
        .btn.secondary{
          background: linear-gradient(135deg, rgba(57,96,65,.35), rgba(127,208,105,.25));
          color: var(--ink); border:1px solid var(--edge);
        }
        .btn::after{
          content:""; position:absolute; inset:0; border-radius:inherit; pointer-events:none;
          background: linear-gradient(115deg, transparent 0%, rgba(255,255,255,.18) 12%, rgba(255,255,255,.6) 18%, rgba(255,255,255,.2) 24%, transparent 30%);
          transform: translateX(-140%); transition: transform .6s ease;
        }
        .btn:hover{ transform: translateY(-1px) scale(1.02); filter:saturate(1.05); }
        .btn:hover::after{ transform: translateX(140%); }
        .btn:focus-visible{ outline:none; box-shadow: 0 0 0 2px #000, 0 0 0 5px rgba(127,208,105,.65); }

        .contribute{ margin-top:.6rem; align-self:flex-start; }
      `}</style>
    </div>
  )
}
