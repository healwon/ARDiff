public class newV {
    public static double snippet(int score) {
        int g = 0;
        g = (score - 60) / 10 + 1;
        g = Math.max(0, Math.min(4, g));
        if (score < 0 || score >= 100) {
            g = -1;
        }
        return g;
    }
}
