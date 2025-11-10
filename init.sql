DROP TABLE IF EXISTS results;

CREATE TABLE results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_status_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME DEFAULT NULL,
    image_blob LONGBLOB DEFAULT NULL
);
