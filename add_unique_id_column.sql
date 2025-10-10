-- Manually add unique_id column to student_simulation_instances
-- Run this in your Neon database

-- Check if column exists first
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'student_simulation_instances' 
        AND column_name = 'unique_id'
    ) THEN
        -- Add the column
        ALTER TABLE student_simulation_instances 
        ADD COLUMN unique_id VARCHAR;
        
        -- Generate unique IDs for existing rows
        UPDATE student_simulation_instances 
        SET unique_id = 'SSI-' || UPPER(SUBSTRING(MD5(RANDOM()::TEXT || id::TEXT) FROM 1 FOR 12))
        WHERE unique_id IS NULL;
        
        -- Make it non-nullable
        ALTER TABLE student_simulation_instances 
        ALTER COLUMN unique_id SET NOT NULL;
        
        -- Add unique index
        CREATE UNIQUE INDEX ix_student_simulation_instances_unique_id 
        ON student_simulation_instances (unique_id);
        
        RAISE NOTICE 'Column unique_id added successfully';
    ELSE
        RAISE NOTICE 'Column unique_id already exists';
    END IF;
END $$;

