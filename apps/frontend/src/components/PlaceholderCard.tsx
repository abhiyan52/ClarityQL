type PlaceholderCardProps = {
  title: string;
  description: string;
};

const PlaceholderCard = ({ title, description }: PlaceholderCardProps) => {
  return (
    <div style={{ border: "1px solid #ddd", padding: "1rem", borderRadius: 8 }}>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
};

export default PlaceholderCard;
