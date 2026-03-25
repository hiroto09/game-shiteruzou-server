CREATE TABLE digital_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    status_id INT,
    start_time DATETIME,
    end_time DATETIME
);

CREATE TABLE analog_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    tag_id VARCHAR(50),
    start_time DATETIME,
    end_time DATETIME
);