# --- 変数定義 ---
DB_CONTAINER=game-siteruzou-db
DB_NAME=game_results
DB_USER=root

# --- コマンド定義 ---
up:
	@echo "🚀 コンテナを起動中..."
	docker compose up -d --build
	@echo "✅ コンテナ起動完了"

down:
	@echo "🧹 コンテナを停止中..."
	docker compose down
	@echo "✅ 停止完了（DBデータは保持されています）"

build:
	@echo "🔧 ビルド中..."
	docker compose build
	@echo "✅ ビルド完了"

logs:
	docker compose logs -f

db-check:
	@echo "🔍 DB存在チェック中..."
	@if docker exec $(DB_CONTAINER) mysql -u$(DB_USER) -p$$DB_PASSWORD -e "USE $(DB_NAME);" 2>/dev/null; then \
		echo "✅ DB $(DB_NAME) は既に存在します"; \
	else \
		echo "⚙️ DB $(DB_NAME) が存在しないため作成します..."; \
		docker exec $(DB_CONTAINER) mysql -u$(DB_USER) -p$$DB_PASSWORD -e "CREATE DATABASE $(DB_NAME);" ; \
	fi

ps:
	docker compose ps

restart:
	docker compose restart

clean:
	@echo "🧨 全てのコンテナとボリュームを削除します..."
	docker compose down -v
