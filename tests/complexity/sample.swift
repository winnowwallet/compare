struct S {
  init(x: Int) { self.x = x }
  var c: Int { get { a ?? 1 } }
  subscript(i: Int) -> Int { i }
  func f(a: Int?, b: Bool) throws -> Int {
    guard let a = a else { return 0 }
    let g = { (y: Int) in y > 1 ? 1 : 0 }
    for i in 0..<3 where i > 0 { if a > 1 && b || !b { continue } }
    while b { break }
    repeat { } while false
    switch a { case 1, 2: return 1; case 3: return 2; default: return 0 }
    do { try h() } catch let e as E { } catch { }
    return g(a) ?? 0
  }
}
