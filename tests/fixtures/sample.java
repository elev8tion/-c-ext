package com.example;

import java.util.List;
import java.util.ArrayList;

public class TaskManager {
    private List<String> tasks;

    public TaskManager() {
        this.tasks = new ArrayList<>();
    }

    public void addTask(String task) {
        tasks.add(task);
    }

    public List<String> getTasks() {
        return tasks;
    }
}

interface Runnable {
    void execute();
    boolean isComplete();
}

enum Priority {
    LOW,
    MEDIUM,
    HIGH,
    CRITICAL
}
