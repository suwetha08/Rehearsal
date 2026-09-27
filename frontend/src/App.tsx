import { useEffect, useState, useRef } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Clock, CheckCircle2, User, Loader2 } from 'lucide-react'
import clsx from 'clsx'

// ── Types ──────────────────────────────────────────────────────────────────
type PressureTier = 'calm' | 'pressing' | 'critical'
type RoomState = 'waiting_room' | 'round_in_progress' | 'round_summary' | 'generating'

interface RoomData {
  room_id: string
  state: RoomState
  round: number
  domain: string
  difficulty: string
  host_id: string
  panel_pressure_score: number
  current_question: string | null
  connected_clients: string[]
  responses_this_round: string[]
}

interface ChatMessage {
  id: string
  client_id: string
  message: string
}

// ── Helpers ─────────────────────────────────────────────────────────────────
const getPressureTier = (score: number): PressureTier => {
  if (score < 40) return 'calm'
  if (score <= 70) return 'pressing'
  return 'critical'
}

const getTierColorClass = (tier: PressureTier) => {
  switch (tier) {
    case 'calm': return 'text-pressure-calm bg-pressure-calm/10 border-pressure-calm/20 shadow-[0_0_15px_rgba(45,212,191,0.15)]'
    case 'pressing': return 'text-pressure-pressing bg-pressure-pressing/10 border-pressure-pressing/20 shadow-[0_0_15px_rgba(245,158,11,0.15)]'
    case 'critical': return 'text-pressure-critical bg-pressure-critical/10 border-pressure-critical/20 shadow-[0_0_15px_rgba(224,108,117,0.15)]'
  }
}

// ── Components ──────────────────────────────────────────────────────────────

export default function App() {
  const [clientId, setClientId] = useState('')
  const [roomCodeInput, setRoomCodeInput] = useState('')
  const [role, setRole] = useState<'participant' | 'host'>('participant')
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  
  const [roomData, setRoomData] = useState<RoomData | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  
  const wsRef = useRef<WebSocket | null>(null)

  const connect = (e: React.FormEvent) => {
    e.preventDefault()
    if (!clientId.trim()) return

    if (role === 'participant' && !roomCodeInput.trim()) {
      setErrorMsg("Room code is required for participants.")
      return
    }

    setErrorMsg(null)

    const ws = new WebSocket(`ws://localhost:8000/ws/${clientId}?domain=backend&role=${role}&room_code=${roomCodeInput.trim()}`)
    
    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data)
      
      if (payload.type === 'error') {
        if (payload.reason === 'host_taken') {
          setErrorMsg("This room already has a host.")
          ws.close()
        } else if (payload.reason === 'room_not_found') {
          setErrorMsg("Room not found. Check the code.")
          ws.close()
        } else if (payload.reason === 'incomplete_responses') {
          setErrorMsg(payload.message)
        }
        return
      }

      if (payload.type === 'state_change') {
        setRoomData(payload as RoomData)
      } else if (payload.type === 'host_update') {
        setRoomData(prev => prev ? { ...prev, host_id: payload.host_id } : null)
      } else if (payload.type === 'chat') {
        setMessages(prev => [...prev, { id: crypto.randomUUID(), ...payload }])
      } else if (payload.type === 'pressure_update') {
        setRoomData(prev => prev ? { ...prev, panel_pressure_score: payload.panel_pressure_score, difficulty: payload.next_difficulty } : null)
      } else if (payload.type === 'question_token') {
        setRoomData(prev => {
          if (!prev) return null
          return { ...prev, current_question: (prev.current_question || '') + payload.token }
        })
      } else if (payload.type === 'question_complete') {
        setRoomData(prev => prev ? { ...prev, current_question: payload.question } : null)
      }
    }

    ws.onopen = () => setIsConnected(true)
    ws.onclose = () => {
      setIsConnected(false)
      setRoomData(null)
    }
    wsRef.current = ws
  }

  const advanceState = () => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'advance_state' }))
    }
  }

  const sendChat = (e: React.FormEvent) => {
    e.preventDefault()
    if (!draft.trim() || !wsRef.current) return
    wsRef.current.send(JSON.stringify({ type: 'chat', message: draft }))
    setDraft('')
  }

  // ── Render ────────────────────────────────────────────────────────────────

  if (!isConnected) {
    return (
      <div className="min-h-screen flex flex-col md:flex-row bg-background text-zinc-300 relative overflow-hidden">
        {/* Enhanced Visible Grid */}
        <div className="absolute inset-0 pointer-events-none bg-[linear-gradient(to_right,rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:64px_64px] z-0" />
        
        {/* Scanline */}
        <div className="absolute inset-0 pointer-events-none h-full w-full opacity-20 animate-scanline bg-gradient-to-b from-transparent via-pressure-calm/10 to-transparent z-0" />

        {/* Left Side - Typography Anchor */}
        <div className="flex-1 flex flex-col justify-center p-8 md:p-16 relative z-10">
          <h1 className="text-6xl md:text-8xl lg:text-9xl font-semibold tracking-tighter text-white mb-6">
            Rehearsal<span className="text-pressure-calm">.</span>
          </h1>
          <p className="font-mono text-sm md:text-base uppercase tracking-[0.2em] text-zinc-500">
            Multi-Agent Panel Simulator // Mission Control
          </p>
        </div>

        {/* Right Side - Entry Panel */}
        <div className="w-full md:w-[480px] bg-black/60 border-t md:border-t-0 md:border-l border-zinc-900/80 backdrop-blur-xl p-8 md:p-16 flex flex-col justify-center relative z-10 shadow-[-20px_0_40px_rgba(0,0,0,0.5)]">
          <form onSubmit={connect} className="space-y-10">
            <div className="space-y-4">
              <label className="font-mono text-xs uppercase tracking-widest text-zinc-500 flex items-center gap-3">
                <div className="w-1.5 h-1.5 bg-pressure-calm rounded-full animate-pulse" />
                Operator Callsign
              </label>
              <input
                type="text"
                value={clientId}
                onChange={e => setClientId(e.target.value)}
                className="w-full bg-transparent border-b-2 border-zinc-800 px-0 py-4 text-xl md:text-2xl focus:outline-none focus:border-pressure-calm transition-colors placeholder:text-zinc-800 font-mono text-white rounded-none"
                placeholder="Enter callsign..."
                autoFocus
              />
            </div>
            
            <div className="space-y-4">
              <div className="space-y-2">
                <div className="flex p-1 bg-black/40 border border-zinc-800/80 rounded-lg">
                  <button 
                    type="button" 
                    onClick={() => { setRole('participant'); setErrorMsg(null); }} 
                    className={clsx("flex-1 py-2.5 text-[10px] font-bold uppercase tracking-widest rounded-md transition-all", role === 'participant' ? "bg-zinc-800 text-white shadow-sm" : "text-zinc-500 hover:text-zinc-300")}
                  >
                    Join as Participant
                  </button>
                  <button 
                    type="button" 
                    onClick={() => { setRole('host'); setErrorMsg(null); }} 
                    className={clsx("flex-1 py-2.5 text-[10px] font-bold uppercase tracking-widest rounded-md transition-all", role === 'host' ? "bg-pressure-calm text-zinc-950 shadow-[0_0_15px_rgba(45,212,191,0.2)]" : "text-zinc-500 hover:text-zinc-300")}
                  >
                    Join as Host
                  </button>
                </div>
              </div>

              <div className="space-y-4 pt-4">
                <label className="font-mono text-xs uppercase tracking-widest text-zinc-500 flex items-center gap-3">
                  <div className="w-1.5 h-1.5 bg-zinc-700 rounded-full" />
                  Room Code
                </label>
                <input
                  type="text"
                  value={roomCodeInput}
                  onChange={e => setRoomCodeInput(e.target.value.toUpperCase())}
                  className="w-full bg-transparent border-b-2 border-zinc-800 px-0 py-4 text-xl focus:outline-none focus:border-zinc-500 transition-colors placeholder:text-zinc-800 font-mono text-white rounded-none uppercase"
                  placeholder={role === 'host' ? "Leave blank to create a new room" : "Enter room code"}
                />
              </div>

              {errorMsg && (
                <p className="text-pressure-critical text-xs font-semibold animate-pulse">{errorMsg}</p>
              )}
            </div>
            
            <button
              type="submit"
              disabled={!clientId.trim()}
              className="w-full relative group disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {/* Button Glow Backdrop */}
              <div className="absolute inset-0 bg-pressure-calm opacity-20 blur-xl group-hover:opacity-40 transition-opacity duration-500 rounded" />
              {/* Button Surface */}
              <div className="relative w-full bg-pressure-calm text-zinc-950 font-bold px-6 py-5 rounded text-sm hover:brightness-110 active:scale-[0.98] transition-all uppercase tracking-widest flex justify-between items-center">
                <span>Initialize Session</span>
                <span>→</span>
              </div>
            </button>
          </form>
        </div>
      </div>
    )
  }

  if (!roomData) return <div className="min-h-screen flex items-center justify-center bg-background"><Loader2 className="animate-spin text-zinc-500" /></div>

  const pressureTier = getPressureTier(roomData.panel_pressure_score)
  const isHost = roomData.host_id === clientId

  return (
    <div className="min-h-screen flex flex-col md:flex-row relative overflow-hidden text-zinc-300 bg-background">
      
      {/* ── Main Canvas (Left/Top) ────────────────────────────────────────── */}
      <main className="flex-1 p-8 md:p-12 lg:p-16 flex flex-col relative z-10">
        
        {/* Top Header Row */}
        <header className="flex items-center justify-between mb-16">
          <div className="flex items-center gap-4">
            <h1 className="text-sm font-semibold tracking-wide uppercase text-zinc-500">Rehearsal</h1>
            <div className="h-4 w-[1px] bg-zinc-800" />
            <span className="font-mono text-xs text-zinc-500">ROOM:{roomData.room_id}</span>
          </div>
          
          {/* Panel Mood Indicator */}
          <div className="relative">
            {/* Dynamic Glow Layer */}
            <div className={clsx(
              "absolute inset-0 rounded-full blur-md opacity-50 animate-pulse-glow transition-all duration-700",
              pressureTier === 'calm' && "bg-pressure-calm",
              pressureTier === 'pressing' && "bg-pressure-pressing",
              pressureTier === 'critical' && "bg-pressure-critical blur-lg opacity-80"
            )} />
            <motion.div 
              layout
              className={clsx(
                "relative flex items-center gap-3 px-4 py-2 rounded-full border transition-all duration-500 ease-out z-10 bg-background/80 backdrop-blur-sm",
                getTierColorClass(pressureTier)
              )}
            >
              <Activity size={16} className="shrink-0" />
              <div className="flex items-baseline gap-2">
                <span className="text-xs font-semibold uppercase tracking-widest">{pressureTier}</span>
                <span className="font-mono font-bold text-sm">{roomData.panel_pressure_score.toFixed(1)}</span>
              </div>
            </motion.div>
          </div>
        </header>

        {/* Center Stage: The Question */}
        <div className="flex-1 flex flex-col justify-center max-w-4xl">
          <AnimatePresence mode="wait">
            {roomData.state === 'waiting_room' && (
              <motion.div
                key="waiting"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                className="space-y-6"
              >
                <h2 className="text-3xl md:text-5xl font-semibold tracking-tight text-white leading-tight">
                  Waiting for panel to assemble.
                </h2>
                
                {isHost && (
                  <div className="my-8 p-6 bg-black/40 border border-zinc-800 rounded-xl inline-block">
                    <p className="text-xs font-bold uppercase tracking-widest text-zinc-500 mb-2">Invite Participants</p>
                    <div className="flex items-center gap-4">
                      <span className="font-mono text-5xl tracking-[0.2em] text-white selection:bg-pressure-calm selection:text-black">
                        {roomData.room_id}
                      </span>
                      <button 
                        onClick={() => navigator.clipboard.writeText(roomData.room_id)}
                        className="p-3 bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white rounded-lg transition-colors cursor-pointer"
                        title="Copy Room Code"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                      </button>
                    </div>
                  </div>
                )}

                <p className="text-zinc-500 max-w-lg text-lg">
                  When the host begins the session, the AI interviewer will calibrate its first question.
                </p>
                {isHost ? (
                  <button 
                    onClick={advanceState}
                    className="bg-zinc-100 text-zinc-950 font-semibold px-6 py-3 rounded-md text-sm hover:bg-white transition-all active:scale-[0.98]"
                  >
                    Start Session
                  </button>
                ) : (
                  <p className="text-zinc-400 italic mt-6">
                    Waiting for host ({roomData.host_id}) to start...
                  </p>
                )}
              </motion.div>
            )}

            {roomData.state === 'generating' && (
              <motion.div
                key="generating"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-4 text-zinc-400"
              >
                <Loader2 size={24} className="animate-spin" />
                <span className="font-mono text-sm uppercase tracking-widest">Synthesizing Question...</span>
              </motion.div>
            )}

            {roomData.state === 'round_in_progress' && (
              <motion.div
                key="live"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-8"
              >
                <div className="flex items-center gap-3 font-mono text-xs text-zinc-500 uppercase tracking-widest mb-4">
                  <span className="text-zinc-400">Round 0{roomData.round}</span>
                  <span>/</span>
                  <span>{roomData.difficulty}</span>
                </div>
                
                {/* Huge Typography for Question */}
                <h2 className="text-3xl md:text-5xl lg:text-6xl font-semibold tracking-tight text-zinc-100 leading-[1.1] selection:bg-zinc-800">
                  {roomData.current_question}
                </h2>

                {isHost && (
                  <div className="pt-8 flex items-center gap-6">
                    <button 
                      onClick={() => { setErrorMsg(null); advanceState(); }}
                      className="bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 font-semibold px-5 py-2.5 rounded-md text-xs uppercase tracking-widest transition-all active:scale-[0.98] flex items-center gap-2"
                    >
                      Force Advance
                    </button>
                    {errorMsg && (
                      <p className="text-pressure-critical text-xs font-semibold">{errorMsg}</p>
                    )}
                  </div>
                )}
              </motion.div>
            )}

            {roomData.state === 'round_summary' && (
              <motion.div
                key="summary"
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="space-y-6"
              >
                <h2 className="text-3xl md:text-5xl font-semibold tracking-tight text-white leading-tight">
                  Round complete.
                </h2>
                <p className="text-zinc-500 text-lg">
                  The panel pressure score is now <strong className="font-mono text-white">{roomData.panel_pressure_score.toFixed(1)}</strong>. 
                  Next round difficulty: <strong className="text-white uppercase">{roomData.difficulty}</strong>.
                </p>
                {isHost ? (
                  <button 
                    onClick={advanceState}
                    className="bg-zinc-100 text-zinc-950 font-semibold px-6 py-3 rounded-md text-sm hover:bg-white transition-all active:scale-[0.98]"
                  >
                    Start Next Round
                  </button>
                ) : (
                  <p className="text-zinc-400 italic mt-6">
                    Waiting for host ({roomData.host_id}) to advance...
                  </p>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Answer Input Area (Only visible during live round) */}
        <AnimatePresence>
          {roomData.state === 'round_in_progress' && !roomData.responses_this_round.includes(clientId) && (
            <motion.form 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              onSubmit={sendChat} 
              className="mt-12 relative max-w-3xl"
            >
              <textarea
                value={draft}
                onChange={e => setDraft(e.target.value)}
                placeholder="Draft your response..."
                className="w-full bg-panel border border-zinc-800/80 rounded-lg p-5 text-sm resize-none focus:outline-none focus:border-zinc-600 focus:ring-1 focus:ring-zinc-600 transition-colors min-h-[120px]"
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChat(e);
                  }
                }}
              />
              <div className="absolute bottom-4 right-4 flex items-center gap-3">
                <span className="font-mono text-xs text-zinc-500">Press Enter</span>
                <button 
                  type="submit" 
                  disabled={!draft.trim()}
                  className="bg-zinc-200 text-zinc-950 font-semibold px-4 py-2 rounded text-xs hover:bg-white disabled:opacity-50 transition-all active:scale-[0.98]"
                >
                  Submit
                </button>
              </div>
            </motion.form>
          )}
        </AnimatePresence>

      </main>

      {/* ── Side Rail: Presence (Right/Bottom) ────────────────────────────── */}
      <aside className="w-full md:w-80 border-t md:border-t-0 md:border-l border-zinc-900 bg-zinc-950/50 flex flex-col relative z-20">
        <div className="p-6 border-b border-zinc-900">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-zinc-500">Panel Presence</h3>
        </div>
        
        <ul className="flex-1 overflow-y-auto p-4 space-y-2">
          {roomData.connected_clients.map(client => {
            const hasAnswered = roomData.responses_this_round.includes(client)
            const isMe = client === clientId
            const isClientHost = roomData.host_id === client
            
            return (
              <li 
                key={client}
                className="flex items-center gap-4 p-3 rounded-md hover:bg-zinc-900/50 transition-colors"
              >
                {/* Avatar */}
                <div className={clsx(
                  "w-10 h-10 rounded-full flex items-center justify-center font-mono text-sm shrink-0",
                  isMe ? "bg-zinc-800 text-zinc-200" : "bg-zinc-900 text-zinc-500"
                )}>
                  {client.charAt(0).toUpperCase()}
                </div>
                
                {/* Info */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className={clsx("font-semibold text-sm truncate flex items-center gap-2", isMe ? "text-zinc-200" : "text-zinc-400")}>
                      {client} 
                      {isMe && <span className="text-zinc-600 font-normal">(You)</span>}
                      {isClientHost && (
                        <span className="text-[10px] uppercase font-bold text-pressure-calm tracking-widest px-1.5 py-0.5 rounded border border-pressure-calm/30 bg-pressure-calm/10">Host</span>
                      )}
                    </span>
                  </div>
                  
                  {/* Status Text */}
                  <div className="text-xs mt-0.5">
                    {roomData.state === 'round_in_progress' ? (
                      hasAnswered ? (
                        <span className="flex items-center gap-1.5 text-emerald-500/90 font-medium">
                          <CheckCircle2 size={12} /> Response locked
                        </span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-amber-500/90">
                          <Clock size={12} /> Formulating...
                        </span>
                      )
                    ) : (
                      <span className="text-zinc-600">Standing by</span>
                    )}
                  </div>
                </div>
              </li>
            )
          })}
        </ul>
      </aside>

    </div>
  )
}

