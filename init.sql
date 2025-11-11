-- 結果テーブル（画像カラム削除済）
CREATE TABLE results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_status_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME DEFAULT NULL
);

CREATE TABLE images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    image_url VARCHAR(255) NOT NULL,
    saved_time DATETIME NOT NULL
);

