// Who is logged in (from `GET /api/me`). App sets it after login; Settings → Server
// Admin updates it when multi-user mode is switched. Single-user mode: every
// login is the owner, an admin.

import { useEffect, useState } from 'react'
import type { Me, Role } from './types'

export interface Account {
  multiUser: boolean
  username: string | null
  role: Role
  /** The server owner (root library; logs in with the server password). */
  owner: boolean
}

const EVENT = 'lxw-account'
const SINGLE: Account = { multiUser: false, username: null, role: 'admin', owner: true }
let current: Account = SINGLE

export function accountFrom(me: Me): Account {
  return { multiUser: me.multi_user, username: me.username, role: me.role ?? 'admin', owner: me.owner }
}

export function setAccount(next: Account): void {
  current = next
  window.dispatchEvent(new CustomEvent<Account>(EVENT, { detail: next }))
}

export function getAccount(): Account {
  return current
}

export function useAccount(): Account {
  const [account, setLocal] = useState(current)
  useEffect(() => {
    const handler = (e: Event) => setLocal((e as CustomEvent<Account>).detail)
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
  return account
}
