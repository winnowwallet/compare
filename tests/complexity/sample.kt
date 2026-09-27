class K(val x: Int) {
  constructor() : this(0) { if (x > 0) println() }
  init { if (x > 1) println() }
  val p: Int get() = if (x > 0) 1 else 2
  fun f(a: Int?, b: Boolean): Int {
    val g = { y: Int -> if (y > 1) 1 else 0 }
    for (i in 0..3) { if (a != null && b || !b) continue }
    while (b) break
    do { } while (false)
    try { h() } catch (e: Exception) { }
    return when (a) { 1, 2 -> 1; 3 -> 2; else -> g(a ?: 0) }
  }
}
