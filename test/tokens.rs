//! Token eyeball fixture: comments, strings, numbers, functions, types,
//! attributes, operators, punctuation, macros.

use std::collections::HashMap;

/// A runner on the grid (doc comment).
#[derive(Debug, Clone, PartialEq)]
pub struct NeonRunner {
    pub id: u32,
    pub handle: String,
    pub ratio: f64,
}

pub enum GridState {
    Online,
    Offline(u8),
    Linked { peers: usize },
}

pub trait Jack {
    fn jack_in(&self) -> Result<u32, String>;
}

impl Jack for NeonRunner {
    fn jack_in(&self) -> Result<u32, String> {
        // numbers: decimal, hex, binary, float, escape in string
        let hex = 0x1f;
        let bits = 0b1010_0101;
        let boost = 3.14_f64 * self.ratio;
        let msg = format!("runner {} @ {:.2}\n\t<{}>", self.handle, boost, self.id);
        println!("{}", msg);

        let mut table: HashMap<&str, u32> = HashMap::new();
        table.insert("neon", 11);

        if self.id >= 42 && hex != 0 || bits < 255 {
            Ok((self.id << 2) | (bits as u32) & 0xff)
        } else {
            Err(String::from("offline: \"no carrier\""))
        }
    }
}
