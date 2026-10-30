import Std
/-! A module comment: if while catch && || | x => 1 -/

namespace Sample

-- if, &&, ||, for, while, unless, catch, else if; a `match` with two non-wildcard arms and `_`;
-- an or-pattern is one arm; a `fun` with one non-wildcard alternative; the `where` helper's if
def f (xs : List Nat) (s : String) : IO Nat := do
  let label := s!"if {(xs.map fun x => s!"\"{x}|\"").length} || ok"  -- a string, not code: if || |
  let c := '|'
  if xs.isEmpty && s.isEmpty || s == "if" then return 0
  else if s.length > 3 then return 1
  for x in xs do
    unless x > 0 do pure ()
  while false do pure ()
  try pure () catch _ => pure ()
  let n := match xs with
    | [] => 0
    | [_] | [_, _] => 1
    | _ => 2
  let g := fun
    | 0 => 1
    | _ => 0
  return n + g 0 + helper label.length + c.toNat
where
  helper (k : Nat) : Nat := if k > 0 then k else 0

/-- A definition by patterns: two non-wildcard arms. -/
def g : Nat → Nat
  | 0 => 0
  | 1 => 1
  | _ => 2

instance : ToString Bool := ⟨fun b => if b then "t" else "f"⟩

theorem g_zero : g 0 = 0 := by
  simp [g]

end Sample
