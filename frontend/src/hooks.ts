import { useState } from 'react'

export function useAsync() {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const run = async (fn: () => Promise<void>, opts?: { silent?: boolean }) => {
    if (!opts?.silent) setBusy(true)
    setError('')
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      if (!opts?.silent) setBusy(false)
    }
  }

  return { busy, error, setError, run }
}
