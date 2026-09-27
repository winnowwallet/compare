impl S { fn m(&self) -> u8 { let g = |y: u8| if y > 1 { 1 } else { 0 }; for i in 0..3 { if i > 1 && true || false { continue } } while false {} loop { break } match self.x { 1 | 2 => 1, n if n > 3 => 2, _ => g(0) } } }
fn f() -> Result<u8, E> { let v = h()?; Ok(v) }
trait T { fn d(&self) { if true {} } }
