public class newV {
    public static double snippet(int price, int age) {
        int pay = 0;
        boolean child = age < 12;
        boolean senior = age > 65;
        pay = price;
        if (child || senior) {
            pay = price / 2;
        }
        return pay;
    }
}
