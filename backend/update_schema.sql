-- Migration: Add time_slots table for appointment slot management
-- Run this against your 'hospital' database in the 'hospital' schema

SET search_path TO hospital, public;

-- Time slots table: each row is a bookable 30-min slot for a doctor
CREATE TABLE IF NOT EXISTS time_slots (
    id SERIAL PRIMARY KEY,
    doctor_id INTEGER REFERENCES doctors(id),
    slot_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    is_available BOOLEAN DEFAULT TRUE
);

-- Update appointments table to optionally reference a time_slot
ALTER TABLE appointments ADD COLUMN IF NOT EXISTS slot_id INTEGER REFERENCES time_slots(id);

-- Generate dummy slots for the next 14 days
-- Dr. Alice Smith (id=1): Mon-Wed-Fri: 10:00 AM - 02:00 PM (30-min slots)
-- Dr. John Doe (id=2): Tue-Thu: 09:00 AM - 01:00 PM
-- Dr. Robert Brown (id=3): Mon-Fri: 09:00 AM - 05:00 PM
-- Dr. Emily White (id=4): Mon-Wed-Fri: 01:00 PM - 05:00 PM
-- Dr. Michael Green (id=5): Mon-Sat: 10:00 AM - 04:00 PM

DO $$
DECLARE
    d DATE;
    dow INT; -- 0=Sun, 1=Mon, ..., 6=Sat
    t TIMESTAMP;
    slot_start TIME;
    slot_end TIME;
BEGIN
    FOR d IN SELECT gs::date FROM generate_series(CURRENT_DATE, CURRENT_DATE + 13, '1 day') gs LOOP
        dow := EXTRACT(DOW FROM d);

        -- Dr. Alice Smith (id=1): Mon(1), Wed(3), Fri(5) 10:00-14:00
        IF dow IN (1, 3, 5) THEN
            FOR t IN SELECT gs FROM generate_series(d + '10:00'::time, d + '13:30'::time, '30 minutes'::interval) gs LOOP
                slot_start := t::time;
                slot_end := (t + '30 minutes'::interval)::time;
                INSERT INTO time_slots (doctor_id, slot_date, start_time, end_time, is_available)
                VALUES (1, d, slot_start, slot_end, TRUE);
            END LOOP;
        END IF;

        -- Dr. John Doe (id=2): Tue(2), Thu(4) 09:00-13:00
        IF dow IN (2, 4) THEN
            FOR t IN SELECT gs FROM generate_series(d + '09:00'::time, d + '12:30'::time, '30 minutes'::interval) gs LOOP
                slot_start := t::time;
                slot_end := (t + '30 minutes'::interval)::time;
                INSERT INTO time_slots (doctor_id, slot_date, start_time, end_time, is_available)
                VALUES (2, d, slot_start, slot_end, TRUE);
            END LOOP;
        END IF;

        -- Dr. Robert Brown (id=3): Mon(1)-Fri(5) 09:00-17:00
        IF dow BETWEEN 1 AND 5 THEN
            FOR t IN SELECT gs FROM generate_series(d + '09:00'::time, d + '16:30'::time, '30 minutes'::interval) gs LOOP
                slot_start := t::time;
                slot_end := (t + '30 minutes'::interval)::time;
                INSERT INTO time_slots (doctor_id, slot_date, start_time, end_time, is_available)
                VALUES (3, d, slot_start, slot_end, TRUE);
            END LOOP;
        END IF;

        -- Dr. Emily White (id=4): Mon(1), Wed(3), Fri(5) 13:00-17:00
        IF dow IN (1, 3, 5) THEN
            FOR t IN SELECT gs FROM generate_series(d + '13:00'::time, d + '16:30'::time, '30 minutes'::interval) gs LOOP
                slot_start := t::time;
                slot_end := (t + '30 minutes'::interval)::time;
                INSERT INTO time_slots (doctor_id, slot_date, start_time, end_time, is_available)
                VALUES (4, d, slot_start, slot_end, TRUE);
            END LOOP;
        END IF;

        -- Dr. Michael Green (id=5): Mon(1)-Sat(6) 10:00-16:00
        IF dow BETWEEN 1 AND 6 THEN
            FOR t IN SELECT gs FROM generate_series(d + '10:00'::time, d + '15:30'::time, '30 minutes'::interval) gs LOOP
                slot_start := t::time;
                slot_end := (t + '30 minutes'::interval)::time;
                INSERT INTO time_slots (doctor_id, slot_date, start_time, end_time, is_available)
                VALUES (5, d, slot_start, slot_end, TRUE);
            END LOOP;
        END IF;

    END LOOP;
END $$;
