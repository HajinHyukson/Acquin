"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";

/** Add the given ticker to an existing or new watchlist (stock-page control). */
export default function AddToWatchlist({ ticker }: { ticker: string }) {
  const [lists, setLists] = useState<any[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [newName, setNewName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  async function load() {
    try {
      const data = (await api.watchlists()).data;
      setLists(data);
      if (data.length && !selected) setSelected(data[0].name);
    } catch {
      /* API may be down; control stays inert */
    }
  }

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function add(name: string) {
    if (!name) return;
    setMsg(null);
    try {
      await api.addWatchlistItem(name, ticker);
      setMsg(`'${name}'에 추가됨`);
      load();
    } catch (e: any) {
      setMsg("추가 실패: " + e.message);
    }
  }

  async function createAndAdd() {
    const name = newName.trim();
    if (!name) return;
    try {
      await api.createWatchlist(name).catch(() => {}); // ignore "already exists"
      await add(name);
      setNewName("");
    } catch (e: any) {
      setMsg("실패: " + e.message);
    }
  }

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}>★ 관심종목 추가</button>
    );
  }

  return (
    <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
      {lists.length > 0 && (
        <>
          <select value={selected} onChange={(e) => setSelected(e.target.value)}>
            {lists.map((w) => (
              <option key={w.name} value={w.name}>{w.name}</option>
            ))}
          </select>
          <button onClick={() => add(selected)}>추가</button>
          <span className="muted">또는</span>
        </>
      )}
      <input
        placeholder="새 리스트"
        value={newName}
        onChange={(e) => setNewName(e.target.value)}
        style={{ width: 120 }}
      />
      <button onClick={createAndAdd}>생성+추가</button>
      <button onClick={() => setOpen(false)} className="muted" style={{ background: "transparent", border: "none" }}>
        닫기
      </button>
      {msg && <span className="muted">{msg}</span>}
    </div>
  );
}
