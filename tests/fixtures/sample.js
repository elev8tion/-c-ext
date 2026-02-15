import React from 'react';
import { useState, useEffect } from 'react';
import axios from 'axios';

export function fetchUsers(apiUrl) {
  return axios.get(`${apiUrl}/users`);
}

export class ApiClient {
  constructor(baseUrl) {
    this.baseUrl = baseUrl;
  }

  async get(path) {
    const response = await fetch(`${this.baseUrl}${path}`);
    return response.json();
  }

  async post(path, data) {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
    return response.json();
  }
}

const UserCard = ({ user }) => {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="user-card">
      <h3>{user.name}</h3>
      {expanded && <p>{user.email}</p>}
      <button onClick={() => setExpanded(!expanded)}>
        {expanded ? 'Less' : 'More'}
      </button>
    </div>
  );
};

export default UserCard;
