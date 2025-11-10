-- 結果テーブル（画像カラム削除済）
CREATE TABLE results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    room_status_id INT NOT NULL,
    start_time DATETIME NOT NULL,
    end_time DATETIME DEFAULT NULL
);

-- 新しい画像テーブル
CREATE TABLE images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    result_id INT,
    image_url VARCHAR(255) NOT NULL,
    saved_time DATETIME NOT NULL,
    FOREIGN KEY (result_id) REFERENCES results(id) ON DELETE SET NULL
);
