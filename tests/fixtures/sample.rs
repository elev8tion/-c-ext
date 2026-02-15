use std::collections::HashMap;

pub struct Config {
    pub name: String,
    pub values: HashMap<String, String>,
}

impl Config {
    pub fn new(name: &str) -> Self {
        Config {
            name: name.to_string(),
            values: HashMap::new(),
        }
    }

    pub fn get(&self, key: &str) -> Option<&String> {
        self.values.get(key)
    }
}

pub enum Status {
    Active,
    Inactive,
    Pending(String),
}

pub fn process_status(status: &Status) -> &str {
    match status {
        Status::Active => "active",
        Status::Inactive => "inactive",
        Status::Pending(_) => "pending",
    }
}

pub trait Serializable {
    fn serialize(&self) -> String;
    fn deserialize(data: &str) -> Self;
}
