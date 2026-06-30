import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

function Navbar() {
    const [unlabeledCount, setUnlabeledCount] = useState<number | null>(null);

    useEffect(() => {
        fetch("/api/meetings/unlabeled_count")
            .then(r => r.json())
            .then(data => setUnlabeledCount(data["count"]));
    }, []);

    return (
        <nav className="navbar">
            <Link to="/" className="nav-item">Home</Link>
            <Link to="/about" className="nav-item">About</Link>
            <Link to="/admin/meetings" className="nav-item">
                Speaker labeling {unlabeledCount !== null ? `(${unlabeledCount})` : ""}
            </Link>
            <Link to="/videos" className="nav-item">Videos</Link>
        </nav>
    );
}

export default Navbar;
