# Mac mini への設置(1回だけ)

## 1. このリポジトリ専用の Deploy Key を作る(他のリポジトリには効かない)
```sh
ssh-keygen -t ed25519 -f ~/.ssh/lotoanaba_data -N "" -C "lotoanaba-data deploy"
cat ~/.ssh/lotoanaba_data.pub      # → GitHub: jjayck/lotoanaba-data > Settings > Deploy keys > Add (Allow write access にチェック)
cat >> ~/.ssh/config <<'CONF'
Host github-lotoanaba
  HostName github.com
  User git
  IdentityFile ~/.ssh/lotoanaba_data
  IdentitiesOnly yes
CONF
chmod 600 ~/.ssh/config ~/.ssh/lotoanaba_data
```
## 2. clone して dry-run
```sh
git clone git@github-lotoanaba:jjayck/lotoanaba-data.git ~/lotoanaba-data
git -C ~/lotoanaba-data config user.name jjayck
git -C ~/lotoanaba-data config user.email "<GitHubのnoreplyメール>"   # 本名・個人メールは使わない
/usr/bin/python3 -I ~/lotoanaba-data/mac/update_data.py --dry-run
```
## 3. launchd に登録(毎晩22:10)
```sh
sed "s#__HOME__#$HOME#g" ~/lotoanaba-data/mac/com.lotoanaba.update-data.plist > ~/Library/LaunchAgents/com.lotoanaba.update-data.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.lotoanaba.update-data.plist
launchctl kickstart gui/$(id -u)/com.lotoanaba.update-data   # 試し実行
tail ~/lotoanaba-data/mac/update.log
```
停止: `launchctl bootout gui/$(id -u)/com.lotoanaba.update-data`

## セキュリティ上の性質
- 書き込めるのはこの公開リポジトリだけ(Deploy Key)。トークン・パスワードは保存しない
- 公開物は当選番号CSVとmeta.jsonのみ。スクリプトは検証に失敗したら書かない・pushしない(追記のみ許可)
- Mac は launchd(ユーザー権限)で実行。sudo 不要
