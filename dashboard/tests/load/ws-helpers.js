const RC_COOKIE = "sessionid=j8rnx1jsjghcwj9umta86p537kvpzfe7";
const EX_COOKIE = "sessionid=4q9qzoo5mzytotrmcbbbkyn0y7tgttdv";

function setRcCookie(req, _ctx, _ee, next) {
  req.headers ||= {};
  req.headers.Cookie = RC_COOKIE;
  req.headers.Origin = "http://127.0.0.1:8000";
  next();
}
function setExampleCookie(req, _ctx, _ee, next) {
  req.headers ||= {};
  req.headers.Cookie = EX_COOKIE;
  req.headers.Origin = "http://127.0.0.1:8000";
  next();
}
module.exports = { setRcCookie, setExampleCookie };