import { FormEvent, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../../services/api';
export function LoginPage() {
  const navigate = useNavigate(); const [error,setError]=useState(''); const [busy,setBusy]=useState(false);
  async function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();setError('');setBusy(true);const data=new FormData(event.currentTarget);try{await login(String(data.get('email')),String(data.get('password')));navigate('/');}catch(reason){setError(reason instanceof Error?reason.message:'Sign in failed');}finally{setBusy(false);}}
  return <main className="login"><p className="eyebrow">AUTHORIZED ACCESS</p><h1>Sign in</h1><form onSubmit={submit}><label>Email<input name="email" type="email" autoComplete="username" required/></label><label>Password<input name="password" type="password" autoComplete="current-password" minLength={12} required/></label>{error&&<p role="alert" className="error">{error}</p>}<button disabled={busy}>{busy?'Signing in…':'Sign in'}</button></form></main>;
}

