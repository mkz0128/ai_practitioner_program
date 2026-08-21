import { Link } from "react-router-dom";
import { asset } from "../utils/assets.js";

export default function LotCard({ lot }) {
  return (
    <Link
      className="lot-card"
      to={`/lots/${lot.id}`}
      aria-label={`查看${lot.artist}《${lot.title}》拍品明細`}
    >
      <div className="lot-image">
        <img src={lot.image} alt={`${lot.artist}《${lot.title}》`} />
        <span className="lot-tag">{lot.category}</span>
        {lot.locked && (
          <span className="locked">
            <img src={asset("lock.svg")} alt="" />
            訂閱查看成交價
          </span>
        )}
      </div>
      <div className="lot-details">
        <h2>{lot.title}</h2>
        <p>
          {lot.artist} · {lot.era}
        </p>
        <strong>{lot.price}</strong>
        <footer>
          <span>{lot.house}</span>
          <span>{lot.year}</span>
        </footer>
      </div>
    </Link>
  );
}
