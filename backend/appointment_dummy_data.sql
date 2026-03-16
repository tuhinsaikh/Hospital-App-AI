-- Schema for Hospital Appointments

CREATE TABLE IF NOT EXISTS departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS doctors (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    specialization VARCHAR(100),
    availability_schedule TEXT -- Storing as text for simplicity, could be JSONB for structured timing
);

CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(20),
    email VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS appointments (
    id SERIAL PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    patient_id INTEGER REFERENCES patients(id),
    appointment_time TIMESTAMP NOT NULL,
    status VARCHAR(50) DEFAULT 'Scheduled', -- Scheduled, Completed, Cancelled
    reason TEXT
);

-- Dummy Data

INSERT INTO departments (name, description) VALUES
('Dermatology', 'Skin, hair, and nail conditions'),
('Cardiology', 'Heart and cardiovascular system'),
('Orthopedics', 'Bones, joints, ligaments, tendons, and muscles'),
('General Medicine', 'Primary care and general health issues');

INSERT INTO doctors (name, department_id, specialization, availability_schedule) VALUES
('Dr. Alice Smith', 1, 'Dermatologist', 'Mon-Wed-Fri: 10:00 AM - 02:00 PM'),
('Dr. John Doe', 1, 'Skin Specialist', 'Tue-Thu: 09:00 AM - 01:00 PM'),
('Dr. Robert Brown', 2, 'Cardiologist', 'Mon-Fri: 09:00 AM - 05:00 PM'),
('Dr. Emily White', 3, 'Orthopedic Surgeon', 'Mon-Wed-Fri: 01:00 PM - 05:00 PM'),
('Dr. Michael Green', 4, 'General Physician', 'Mon-Sat: 10:00 AM - 04:00 PM');

INSERT INTO patients (name, phone, email) VALUES
('Jane Doe', '555-0100', 'jane.doe@example.com'),
('Mark Johnson', '555-0101', 'mark.j@example.com');

INSERT INTO appointments (doctor_id, patient_id, appointment_time, status, reason) VALUES
(1, 1, '2026-03-20 10:30:00', 'Scheduled', 'Skin rash'),
(3, 2, '2026-03-22 11:00:00', 'Scheduled', 'Routine heart checkup');
